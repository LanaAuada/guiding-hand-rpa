"""
Testes da automação Guiding Hand (somente biblioteca padrão).

Rodar:  python -m unittest -v

Cada teste roda em uma pasta temporária isolada, então não mexe nos dados reais.
Cenários: SUCESSO, DECISÃO (regras de negócio), FALHA (exceções) e LGPD.
"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from src.config import Config
from src.main import executar

AGORA = datetime(2026, 11, 11, 12, 0, 0)
PONTO = (-23.5440, -46.6422)


def det(id_, dispositivo, tipo="buraco", confianca=0.9, dias_atras=0, lat=PONTO[0], lon=PONTO[1]):
    return {
        "id_deteccao": id_, "id_dispositivo": dispositivo, "tipo": tipo, "confianca": confianca,
        "data_hora": (AGORA - timedelta(days=dias_atras)).isoformat(), "latitude": lat, "longitude": lon,
    }


class BaseTeste(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        raiz = Path(self._tmp.name)
        self.cfg = Config(
            pasta_entrada=raiz / "entrada", pasta_processados=raiz / "processados",
            pasta_rejeitados=raiz / "rejeitados", pasta_estado=raiz / "estado",
            pasta_saida=raiz / "saida", pasta_logs=raiz / "logs",
            api_url=None, api_tentativas=2, api_timeout=1, api_espera_base=0, salt="teste", mostrar_na_tela=False,
        )
        self.cfg.pasta_entrada.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def escrever(self, nome, deteccoes):
        (self.cfg.pasta_entrada / nome).write_text(json.dumps({"deteccoes": deteccoes}), encoding="utf-8")

    def rodar(self, data_ref=AGORA):
        return executar(self.cfg, data_ref)

    def geojson(self):
        return json.loads((self.cfg.pasta_saida / "mapa_barreiras.geojson").read_text(encoding="utf-8"))


class TesteSucesso(BaseTeste):
    def test_ct01_tres_oculos_confirmam_barreira_e_publicam_no_mapa(self):
        self.escrever("lote.json", [det("D1", "OCL-1"), det("D2", "OCL-2"), det("D3", "OCL-3")])
        resumo = self.rodar()

        self.assertEqual(resumo["status"], "sucesso")
        self.assertEqual(resumo["barreiras"]["confirmadas"], 1)
        feature = self.geojson()["features"][0]
        self.assertEqual(feature["properties"]["tipo"], "buraco")
        self.assertEqual(feature["properties"]["status"], "confirmada")
        self.assertTrue(any(self.cfg.pasta_saida.glob("relatorio_zeladoria_*.csv")))
        self.assertTrue((self.cfg.pasta_saida / "resumo_execucao.json").exists())

    def test_ct02_arquivo_lido_vai_para_processados(self):
        self.escrever("lote.json", [det("D1", "OCL-1")])
        self.rodar()
        self.assertEqual(list(self.cfg.pasta_entrada.iterdir()), [])
        self.assertEqual(len(list(self.cfg.pasta_processados.iterdir())), 1)

    def test_ct03_csv_com_ponto_e_virgula_e_aceito(self):
        (self.cfg.pasta_entrada / "lote.csv").write_text(
            "id_deteccao;id_dispositivo;data_hora;latitude;longitude;tipo;confianca\n"
            "C1;OCL-1;2026-11-11T10:00:00;-23,5440;-46,6422;poste;0,8\n", encoding="utf-8")
        resumo = self.rodar()
        self.assertEqual(resumo["deteccoes"]["aceitos"], 1)


class TesteDecisao(BaseTeste):
    def test_ct04_dois_oculos_ficam_pendentes_e_fora_do_mapa(self):
        self.escrever("lote.json", [det("D1", "OCL-1"), det("D2", "OCL-2"), det("D3", "OCL-2")])
        resumo = self.rodar()
        self.assertEqual(resumo["barreiras"]["pendentes"], 1)
        self.assertEqual(self.geojson()["features"], [])

    def test_ct05_pessoas_e_carros_sao_ignorados(self):
        self.escrever("lote.json", [det("D1", "OCL-1", "pessoa"), det("D2", "OCL-2", "carro")])
        resumo = self.rodar()
        self.assertEqual(resumo["deteccoes"]["ignorados_moveis"], 2)
        self.assertEqual(resumo["barreiras"]["total_conhecidas"], 0)

    def test_ct06_baixa_confianca_e_descartada(self):
        self.escrever("lote.json", [det(f"D{i}", f"OCL-{i}", confianca=0.3) for i in range(3)])
        resumo = self.rodar()
        self.assertEqual(resumo["deteccoes"]["baixa_confianca"], 3)
        self.assertEqual(resumo["barreiras"]["total_conhecidas"], 0)

    def test_ct07_barreira_sem_deteccao_ha_30_dias_vira_possivelmente_resolvida(self):
        self.escrever("lote.json", [det(f"D{i}", f"OCL-{i}", dias_atras=40) for i in range(3)])
        resumo = self.rodar()
        self.assertEqual(resumo["barreiras"]["possivelmente_resolvidas"], 1)

    def test_ct08_muitas_deteccoes_elevam_prioridade(self):
        self.escrever("lote.json", [det(f"D{i}", f"OCL-{i % 3}", tipo="poste") for i in range(10)])
        self.rodar()
        self.assertEqual(self.geojson()["features"][0]["properties"]["prioridade"], "alta")

    def test_ct09_deteccoes_em_execucoes_diferentes_se_acumulam(self):
        self.escrever("a.json", [det("D1", "OCL-1"), det("D2", "OCL-2")])
        self.assertEqual(self.rodar()["barreiras"]["confirmadas"], 0)
        self.escrever("b.json", [det("D3", "OCL-3")])
        self.assertEqual(self.rodar()["barreiras"]["confirmadas"], 1)


class TesteFalha(BaseTeste):
    def test_ct10_json_corrompido_vai_para_quarentena_e_o_resto_continua(self):
        (self.cfg.pasta_entrada / "ruim.json").write_text('{"deteccoes": [', encoding="utf-8")
        self.escrever("bom.json", [det("D1", "OCL-1"), det("D2", "OCL-2"), det("D3", "OCL-3")])
        resumo = self.rodar()
        self.assertEqual(resumo["status"], "concluida_com_alertas")
        self.assertEqual(resumo["fontes"]["arquivos_rejeitados"], 1)
        self.assertEqual(resumo["barreiras"]["confirmadas"], 1)
        self.assertEqual(len(list(self.cfg.pasta_rejeitados.iterdir())), 1)

    def test_ct11_registros_invalidos_sao_rejeitados_com_motivo_no_log(self):
        self.escrever("lote.json", [
            det("D1", "OCL-1", lat=-22.9),            # fora de São Paulo
            det("D2", "OCL-1", tipo="disco_voador"),  # tipo desconhecido
            {"id_deteccao": "D3"},                    # campos ausentes
            "isto não é um objeto",
        ])
        resumo = self.rodar()
        self.assertEqual(resumo["deteccoes"]["invalidos"], 4)
        log = (self.cfg.pasta_logs / resumo["log"]).read_text(encoding="utf-8")
        self.assertIn("fora da área do piloto", log)
        self.assertIn("campos ausentes", log)

    def test_ct12_duplicadas_nao_contam_duas_vezes(self):
        self.escrever("a.json", [det("D1", "OCL-1"), det("D1", "OCL-1")])
        self.escrever("b.json", [det("D1", "OCL-1")])
        resumo = self.rodar()
        self.assertEqual(resumo["deteccoes"]["duplicados"], 2)
        self.escrever("c.json", [det("D1", "OCL-1")])  # reenvio em outra execução
        self.assertEqual(self.rodar()["deteccoes"]["duplicados"], 1)

    def test_ct13_api_fora_do_ar_tenta_de_novo_e_segue_com_arquivos(self):
        self.cfg.api_url = "http://127.0.0.1:9/deteccoes"  # porta sem serviço
        self.escrever("lote.json", [det("D1", "OCL-1")])
        resumo = self.rodar()
        self.assertEqual(resumo["fontes"]["api"], "indisponivel")
        self.assertEqual(resumo["status"], "concluida_com_alertas")
        self.assertEqual(resumo["deteccoes"]["aceitos"], 1)
        log = (self.cfg.pasta_logs / resumo["log"]).read_text(encoding="utf-8")
        self.assertIn("tentativa 2/2", log)

    def test_ct14_pasta_de_entrada_ausente_e_criada(self):
        self.cfg.pasta_entrada.rmdir()
        resumo = self.rodar()
        self.assertNotEqual(resumo["status"], "falha")
        self.assertTrue(self.cfg.pasta_entrada.exists())

    def test_ct15_estado_corrompido_gera_backup_e_nao_para_a_automacao(self):
        self.cfg.pasta_estado.mkdir(parents=True)
        (self.cfg.pasta_estado / "barreiras.json").write_text("lixo", encoding="utf-8")
        self.escrever("lote.json", [det("D1", "OCL-1")])
        resumo = self.rodar()
        self.assertNotEqual(resumo["status"], "falha")
        self.assertEqual(len(list(self.cfg.pasta_estado.glob("barreiras_corrompido_*.json"))), 1)

    def test_ct16_toda_execucao_entra_na_auditoria(self):
        self.rodar()
        self.rodar()
        linhas = (self.cfg.pasta_logs / "auditoria.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(linhas), 2)


class TesteLGPD(BaseTeste):
    def test_ct17_id_do_dispositivo_nunca_aparece_em_logs_ou_saidas(self):
        self.escrever("lote.json", [det(f"D{i}", f"OCL-SECRETO-{i}") for i in range(3)])
        self.rodar()
        for pasta in (self.cfg.pasta_logs, self.cfg.pasta_saida, self.cfg.pasta_estado):
            for arquivo in pasta.iterdir():
                self.assertNotIn("OCL-SECRETO", arquivo.read_text(encoding="utf-8-sig"), arquivo.name)

    def test_ct18_localizacao_e_generalizada(self):
        self.escrever("lote.json", [det(f"D{i}", f"OCL-{i}", lat=-23.544071, lon=-46.642238) for i in range(3)])
        self.rodar()
        lon, lat = self.geojson()["features"][0]["geometry"]["coordinates"]
        self.assertEqual((lat, lon), (-23.544, -46.6422))


if __name__ == "__main__":
    unittest.main()

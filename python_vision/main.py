"""
main.py — Smart Gym CP04
Fluxo: cartão RFID → SQLite → câmera com YOLO (detecção do equipamento)
+ MediaPipe (pose) → contagem apenas de repetições completas com o equipamento presente.
"""

import threading
import sqlite3
import serial
import cv2
import mediapipe as mp
import tkinter as tk
from tkinter import font as tkfont
from PIL import Image, ImageTk
from datetime import datetime
from ultralytics import YOLO
import os
import time
import numpy as np

# ── Configurações ────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERIAL_PORT = None  # None = modo simulação (sem Arduino, F5/F6 simulam o cartão)
BAUD_RATE = 9600
DB_PATH = os.path.join(BASE_DIR, "smart_gym.db")
CAMERA_INDEX = 0

# ── Configurações de Visão (CP04) ────────────────────────────────────────────
POSE_MODEL_PATH = os.path.join(BASE_DIR, "pose_landmarker_full.task")
YOLO_MODEL_PATH = os.path.join(BASE_DIR, "yolov8n.pt")  # baixado automaticamente na 1ª execução
# Classes COCO aceitas como "equipamento". 67 = cell phone (substituto do halter/anilha).
EQUIPAMENTO_CLASSES = {67: "Celular"}
YOLO_CONFIANCA = 0.40
YOLO_A_CADA_N_FRAMES = 2       # roda o YOLO a cada N frames (desempenho)
EQUIPAMENTO_TOLERANCIA_S = 0.6  # tempo sem detecção antes de considerar o equipamento ausente

# Limiares do ângulo do cotovelo (ombro-cotovelo-pulso)
ANGULO_EXTENSAO = 150  # acima disto: braço estendido
ANGULO_FLEXAO = 50     # abaixo disto: braço flexionado

# ── Cores (Tema Dark Gym) ────────────────────────────────────────────────────
COR_BG = "#0d0d0d"
COR_CARD = "#1a1a2e"
COR_PRIMARIA = "#e94560"
COR_TEXTO = "#eaeaea"
COR_CINZA = "#555555"
COR_VERDE = "#00e676"
COR_AMARELO = "#ffd600"

# ── MediaPipe Setup (Tasks API) ──────────────────────────────────────────────
PoseLandmarker = mp.tasks.vision.PoseLandmarker
PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

POSE_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 7), (0, 4), (4, 5), (5, 6), (6, 8), (9, 10),
    (11, 12), (11, 13), (13, 15), (15, 17), (15, 19), (15, 21), (17, 19),
    (12, 14), (14, 16), (16, 18), (16, 20), (16, 22), (18, 20),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (27, 29), (29, 31), (31, 27),
    (24, 26), (26, 28), (28, 30), (30, 32), (32, 28)
]

# Índices (ombro, cotovelo, pulso) de cada braço
BRACOS = {
    "esquerdo": (11, 13, 15),
    "direito": (12, 14, 16),
}


def criar_pose_landmarker():
    options = PoseLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=POSE_MODEL_PATH),
        running_mode=VisionRunningMode.VIDEO,
        min_pose_detection_confidence=0.6,
        min_pose_presence_confidence=0.6,
        min_tracking_confidence=0.6,
    )
    return PoseLandmarker.create_from_options(options)


# ── Detecção do Equipamento (YOLO) ───────────────────────────────────────────
class DetectorEquipamento:
    def __init__(self):
        self.model = YOLO(YOLO_MODEL_PATH)
        self.reset()

    def reset(self):
        self.caixa = None       # (x1, y1, x2, y2, rotulo, confiança) da última detecção
        self._ultimo_visto = 0.0
        self._frame_idx = 0

    @property
    def presente(self) -> bool:
        return time.monotonic() - self._ultimo_visto <= EQUIPAMENTO_TOLERANCIA_S

    def atualizar(self, frame_bgr):
        self._frame_idx += 1
        if self._frame_idx % YOLO_A_CADA_N_FRAMES:
            return
        res = self.model.predict(frame_bgr, conf=YOLO_CONFIANCA, classes=list(EQUIPAMENTO_CLASSES),
                                 verbose=False)[0]
        melhor = None
        for box in res.boxes:
            conf = float(box.conf[0])
            if melhor is None or conf > melhor[5]:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                melhor = (x1, y1, x2, y2, EQUIPAMENTO_CLASSES[int(box.cls[0])], conf)
        if melhor:
            self.caixa = melhor
            self._ultimo_visto = time.monotonic()
        elif not self.presente:
            self.caixa = None

    def desenhar(self, frame):
        if not self.caixa:
            return
        x1, y1, x2, y2, rotulo, conf = self.caixa
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 230, 118), 2)
        cv2.putText(frame, f"{rotulo} {conf:.0%}", (x1, max(y1 - 8, 15)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 230, 118), 2, cv2.LINE_AA)


# ── Lógica de Movimento ──────────────────────────────────────────────────────
class AnalisadorMovimento:
    """
    Máquina de estados de uma repetição completa: EXTENSÃO → FLEXÃO → EXTENSÃO.
    A repetição só conta se o equipamento esteve presente durante todo o ciclo;
    se o equipamento sumir no meio, o ciclo é descartado.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.count = 0
        self.estagio = None  # None → "extensao" → "flexao" → (conta) → "extensao"
        self.angulo_atual = 0
        self.braco = None

    @staticmethod
    def calcular_angulo(a, b, c):
        """Calcula o ângulo entre ombro(a), cotovelo(b) e pulso(c)."""
        a, b, c = np.array(a), np.array(b), np.array(c)
        radianos = np.arctan2(c[1] - b[1], c[0] - b[0]) - np.arctan2(a[1] - b[1], a[0] - b[0])
        angulo = np.abs(radianos * 180.0 / np.pi)
        if angulo > 180.0:
            angulo = 360 - angulo
        return angulo

    @staticmethod
    def escolher_braco(landmarks, caixa, largura, altura):
        """Usa o braço cujo pulso está mais perto do equipamento; sem equipamento, o mais visível."""
        if caixa:
            cx, cy = (caixa[0] + caixa[2]) / 2 / largura, (caixa[1] + caixa[3]) / 2 / altura
            return min(BRACOS, key=lambda b: (landmarks[BRACOS[b][2]].x - cx) ** 2 +
                                             (landmarks[BRACOS[b][2]].y - cy) ** 2)
        return max(BRACOS, key=lambda b: sum(landmarks[i].visibility for i in BRACOS[b]))

    @property
    def fase(self) -> str:
        return {"extensao": "Extensão", "flexao": "Flexão"}.get(self.estagio, "Posicione-se")

    def atualizar(self, landmarks, equipamento_presente: bool, caixa, largura, altura) -> bool:
        """Retorna True quando uma repetição completa é contabilizada."""
        self.braco = self.escolher_braco(landmarks, caixa, largura, altura)
        o, c, p = (landmarks[i] for i in BRACOS[self.braco])
        self.angulo_atual = self.calcular_angulo([o.x, o.y], [c.x, c.y], [p.x, p.y])

        if not equipamento_presente:
            # Sem equipamento o ciclo em andamento é invalidado.
            self.estagio = None
            return False

        if self.angulo_atual > ANGULO_EXTENSAO:
            if self.estagio == "flexao":
                # Voltou à extensão após flexionar: ciclo completo.
                self.estagio = "extensao"
                self.count += 1
                return True
            self.estagio = "extensao"
        elif self.angulo_atual < ANGULO_FLEXAO and self.estagio == "extensao":
            self.estagio = "flexao"
        return False


# ── DB Helpers ───────────────────────────────────────────────────────────────
def buscar_aluno(uid: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM alunos WHERE uid_cartao = ?", (uid,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def registrar_entrada(aluno_id: int, uid: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("INSERT INTO sessoes (aluno_id, uid_cartao, entrada) VALUES (?, ?, ?)", (aluno_id, uid, agora))
    sessao_id = cur.lastrowid
    conn.commit()
    conn.close()
    return sessao_id


def registrar_saida(sessao_id: int, rep_realizadas: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("UPDATE sessoes SET saida = ?, rep_realizadas = ? WHERE id = ?", (agora, rep_realizadas, sessao_id))
    conn.commit()
    conn.close()


# ── Aplicação Tkinter ─────────────────────────────────────────────────────────
class SmartGymApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Smart Gym — Estação Inteligente")
        self.root.configure(bg=COR_BG)
        self.root.geometry("1000x680")
        self.root.resizable(False, False)

        self._aluno = None
        self._sessao_id = None
        self._camera_ativa = False
        self._cap = None
        self._serial = None
        self._analisador = AnalisadorMovimento()
        self._detector = DetectorEquipamento()
        self._pose = None
        self._pose_ts = 0
        self._lock = threading.Lock()

        self._construir_ui()
        self._iniciar_serial()
        self._iniciar_rfid_thread()

    def _construir_ui(self):
        F = tkfont.Font
        header = tk.Frame(self.root, bg=COR_PRIMARIA, height=60)
        header.pack(fill="x")
        tk.Label(header, text="🏋 SMART GYM | Estação Inteligente", bg=COR_PRIMARIA, fg="white",
                 font=F(family="Helvetica", size=16, weight="bold")).pack(side="left", padx=20, pady=10)
        self._lbl_hora = tk.Label(header, text="", bg=COR_PRIMARIA, fg="white", font=F(family="Helvetica", size=12))
        self._lbl_hora.pack(side="right", padx=20)

        rodape = tk.Frame(self.root, bg="#111111", height=28)
        rodape.pack(fill="x", side="bottom")
        self._lbl_log = tk.Label(rodape, text="Sistema iniciado.", bg="#111111", fg=COR_CINZA,
                                 font=F(family="Helvetica", size=8))
        self._lbl_log.pack(side="left", padx=10, pady=4)

        corpo = tk.Frame(self.root, bg=COR_BG)
        corpo.pack(fill="both", expand=True, padx=20, pady=15)

        # Painel Info (Esquerda)
        self._painel_info = tk.Frame(corpo, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_CINZA)
        self._painel_info.pack(side="left", fill="both", expand=False, ipadx=15, ipady=10, padx=(0, 10))
        self._painel_info.config(width=290)
        self._painel_info.pack_propagate(False)

        self._lbl_status = tk.Label(self._painel_info, text="⏳ AGUARDANDO\nLOGIN", bg=COR_CARD, fg=COR_AMARELO,
                                    font=F(family="Helvetica", size=14, weight="bold"))
        self._lbl_status.pack(pady=(15, 5))

        tk.Frame(self._painel_info, bg=COR_CINZA, height=1).pack(fill="x", padx=10, pady=5)
        self._lbl_nome = tk.Label(self._painel_info, text="—", bg=COR_CARD, fg=COR_TEXTO,
                                  font=F(family="Helvetica", size=16, weight="bold"), wraplength=240)
        self._lbl_nome.pack(pady=(5, 3))

        self._lbl_exercicio = tk.Label(self._painel_info, text="", bg=COR_CARD, fg=COR_PRIMARIA,
                                       font=F(family="Helvetica", size=11))
        self._lbl_exercicio.pack()

        tk.Frame(self._painel_info, bg=COR_CINZA, height=1).pack(fill="x", padx=10, pady=8)
        tk.Label(self._painel_info, text="EQUIPAMENTO (YOLO)", bg=COR_CARD, fg=COR_CINZA,
                 font=F(family="Helvetica", size=9, weight="bold")).pack()
        self._lbl_equip = tk.Label(self._painel_info, text="—", bg=COR_CARD, fg=COR_CINZA,
                                   font=F(family="Helvetica", size=13, weight="bold"))
        self._lbl_equip.pack(pady=(2, 0))

        tk.Frame(self._painel_info, bg=COR_CINZA, height=1).pack(fill="x", padx=10, pady=8)
        tk.Label(self._painel_info, text="REPETIÇÕES COMPLETAS", bg=COR_CARD, fg=COR_CINZA,
                 font=F(family="Helvetica", size=9, weight="bold")).pack()
        self._lbl_reps = tk.Label(self._painel_info, text="0", bg=COR_CARD, fg=COR_VERDE,
                                  font=F(family="Helvetica", size=48, weight="bold"))
        self._lbl_reps.pack()

        self._lbl_meta = tk.Label(self._painel_info, text="", bg=COR_CARD, fg=COR_CINZA,
                                  font=F(family="Helvetica", size=10))
        self._lbl_meta.pack()

        self._lbl_angulo = tk.Label(self._painel_info, text="Ângulo: 0°  |  Fase: —", bg=COR_CARD, fg=COR_AMARELO,
                                    font=F(family="Helvetica", size=10))
        self._lbl_angulo.pack(pady=(4, 0))

        self._btn_logout = tk.Button(self._painel_info, text="⏹ Encerrar Sessão", bg="#2a0a14", fg=COR_PRIMARIA,
                                     font=F(family="Helvetica", size=10, weight="bold"), relief="flat", cursor="hand2",
                                     command=self._encerrar_sessao, state="disabled")
        self._btn_logout.pack(side="bottom", fill="x", padx=15, pady=10)

        # Painel Câmera (Direita)
        self._painel_cam = tk.Frame(corpo, bg="#111111", highlightthickness=1, highlightbackground=COR_CINZA)
        self._painel_cam.pack(side="right", fill="both", expand=True)
        self._canvas_cam = tk.Canvas(self._painel_cam, bg="#111111", highlightthickness=0)
        self._canvas_cam.pack(fill="both", expand=True)
        self._lbl_cam_placeholder = tk.Label(self._canvas_cam,
                                             text="📷\n\nCâmera inativa\nAguardando identificação do aluno",
                                             bg="#111111", fg=COR_CINZA, font=F(family="Helvetica", size=13),
                                             justify="center")
        self._lbl_cam_placeholder.place(relx=0.5, rely=0.5, anchor="center")

        self._atualizar_relogio()

    def _atualizar_relogio(self):
        self._lbl_hora.config(text=datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
        self.root.after(1000, self._atualizar_relogio)

    def _iniciar_serial(self):
        try:
            if SERIAL_PORT is None:
                raise serial.SerialException("Porta serial desativada")
            self._serial = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
        except Exception:
            self._serial = None
            self._log("Modo Simulação (F5 p/ entrar)")
            self.root.bind("<F5>", lambda _: self._processar_uid("A1:B2:C3:D4"))
            self.root.bind("<F6>", lambda _: self._processar_uid("00:00:00:00"))

    def _iniciar_rfid_thread(self):
        def loop():
            while True:
                if self._serial and self._serial.is_open:
                    linha = self._serial.readline().decode(errors="ignore").strip()
                    if linha.startswith("UID:"):
                        linha = linha[4:].strip()
                    if linha and linha != "READY":
                        self.root.after(0, self._processar_uid, linha)
                time.sleep(0.1)

        threading.Thread(target=loop, daemon=True).start()

    def _processar_uid(self, uid: str):
        if self._aluno:
            return
        aluno = buscar_aluno(uid)
        if aluno:
            self._sessao_id = registrar_entrada(aluno["id"], uid)
            self._aluno = aluno
            self._analisador.reset()
            self._detector.reset()
            self._lbl_status.config(text="✅ TREINO\nATIVO", fg=COR_VERDE)
            self._lbl_nome.config(text=f"Bem-vindo,\n{aluno['nome'].split()[0]}!")
            self._lbl_exercicio.config(text=f"🏋 {aluno['exercicio']}")
            self._lbl_meta.config(text=f"/ {aluno['repeticoes']} meta")
            self._lbl_reps.config(text="0")
            self._btn_logout.config(state="normal", text="⏹ Encerrar Sessão")

            # Feedback para o Arduino
            if self._serial and self._serial.is_open:
                self._serial.write(b"OK\n")

            self._iniciar_camera()
            self._log(f"Login: {aluno['nome']}")
        else:
            if self._serial and self._serial.is_open:
                self._serial.write(b"DENY\n")
            self._log(f"Cartão desconhecido: {uid}")

    def _iniciar_camera(self):
        self._camera_ativa = True
        self._cap = cv2.VideoCapture(CAMERA_INDEX)
        # O modo VIDEO exige timestamps crescentes; um landmarker novo por sessão evita conflitos.
        self._pose = criar_pose_landmarker()
        self._pose_ts = 0
        self._lbl_cam_placeholder.place_forget()
        self._atualizar_frame_camera()

    def _parar_camera(self):
        self._camera_ativa = False
        if self._cap:
            self._cap.release()
            self._cap = None
        if self._pose:
            self._pose.close()
            self._pose = None
        self._canvas_cam.delete("all")
        self._lbl_cam_placeholder.place(relx=0.5, rely=0.5, anchor="center")
        self._lbl_equip.config(text="—", fg=COR_CINZA)

    def _desenhar_pose(self, frame, landmarks):
        h, w, _ = frame.shape
        pts = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]
        for a, b in POSE_CONNECTIONS:
            cv2.line(frame, pts[a], pts[b], (245, 66, 230), 2)
        for x, y in pts:
            cv2.circle(frame, (x, y), 4, (245, 117, 66), cv2.FILLED)
        if self._analisador.braco:
            # Destaca o braço que está sendo analisado
            o, c, p = (pts[i] for i in BRACOS[self._analisador.braco])
            cv2.line(frame, o, c, (0, 214, 255), 4)
            cv2.line(frame, c, p, (0, 214, 255), 4)
            cv2.putText(frame, f"{int(self._analisador.angulo_atual)}", (c[0] + 10, c[1] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)

    def _desenhar_hud(self, frame, equipamento_presente: bool):
        if equipamento_presente:
            texto, cor = "EQUIPAMENTO DETECTADO", (0, 200, 0)
        else:
            texto, cor = "AGUARDANDO EQUIPAMENTO", (0, 140, 255)
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 40), cor, -1)
        cv2.putText(frame, texto, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)

        cv2.rectangle(frame, (10, 50), (260, 130), (30, 30, 30), -1)
        cv2.putText(frame, "REPS", (20, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1, cv2.LINE_AA)
        cv2.putText(frame, str(self._analisador.count), (20, 118), cv2.FONT_HERSHEY_SIMPLEX, 1.5,
                    (118, 230, 0), 3, cv2.LINE_AA)
        cv2.putText(frame, "FASE", (120, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1, cv2.LINE_AA)
        fase = self._analisador.fase if equipamento_presente else "Pausado"
        fase = fase.replace("ã", "a")  # cv2.putText não suporta acentos
        cv2.putText(frame, fase, (120, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)

    def _atualizar_status_equipamento(self, presente: bool):
        if presente:
            self._lbl_equip.config(text="✅ Equipamento Detectado", fg=COR_VERDE)
        else:
            self._lbl_equip.config(text="⏳ Aguardando Equipamento", fg=COR_AMARELO)

    def _atualizar_frame_camera(self):
        if not self._camera_ativa or self._cap is None:
            return

        ret, frame = self._cap.read()
        if ret:
            frame = cv2.flip(frame, 1)
            h, w, _ = frame.shape

            # 1. YOLO: o equipamento está em cena?
            self._detector.atualizar(frame)
            presente = self._detector.presente
            self._atualizar_status_equipamento(presente)

            # 2. MediaPipe: pose do aluno
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self._pose_ts = max(self._pose_ts + 1, int(time.monotonic() * 1000))
            res = self._pose.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), self._pose_ts)

            if res.pose_landmarks:
                landmarks = res.pose_landmarks[0]

                # 3. Contagem: só com equipamento e ciclo completo
                if self._analisador.atualizar(landmarks, presente, self._detector.caixa, w, h):
                    self._lbl_reps.config(text=str(self._analisador.count))
                    self._log(f"Repetição completa {self._analisador.count}")

                    meta = int(self._aluno['repeticoes'])
                    if self._analisador.count >= meta:
                        self._log(f"Meta de {meta} batida! Parabéns!")
                        self.root.after(500, self._parar_camera_automaticamente)

                self._desenhar_pose(frame, landmarks)
                self._lbl_angulo.config(
                    text=f"Ângulo: {int(self._analisador.angulo_atual)}°  |  Fase: {self._analisador.fase}")

            self._detector.desenhar(frame)
            self._desenhar_hud(frame, presente)

            # Renderização do Frame no Canvas
            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            cw, ch = self._canvas_cam.winfo_width(), self._canvas_cam.winfo_height()
            if cw > 1:
                img = img.resize((cw, ch), Image.Resampling.LANCZOS)
            self._img_tk = ImageTk.PhotoImage(image=img)
            self._canvas_cam.create_image(0, 0, anchor="nw", image=self._img_tk)

        self.root.after(10, self._atualizar_frame_camera)

    def _parar_camera_automaticamente(self):
        """Para o vídeo ao bater a meta, mas mantém o botão de encerrar ativo."""
        if not self._camera_ativa:
            return
        self._parar_camera()
        self._lbl_status.config(text="🏆 META\nCONCLUÍDA", fg=COR_VERDE)
        self._btn_logout.config(state="normal", text="⏹ Finalizar e Salvar")
        self._log("Treino concluído. Clique em Finalizar para salvar.")

    def _encerrar_sessao(self):
        """Chamado pelo botão. Salva no DB e limpa tudo."""
        with self._lock:
            sessao_id = self._sessao_id
            reps = self._analisador.count
            self._aluno = None
            self._sessao_id = None

        if sessao_id:
            registrar_saida(sessao_id, reps)
            self._log(f"Dados salvos: {reps} reps.")

        self._parar_camera()

        # Reset Total da UI para o próximo
        self._lbl_status.config(text="⏳ AGUARDANDO\nLOGIN", fg=COR_AMARELO)
        self._lbl_nome.config(text="—")
        self._lbl_exercicio.config(text="")
        self._lbl_reps.config(text="0")
        self._lbl_meta.config(text="")
        self._lbl_angulo.config(text="Ângulo: 0°  |  Fase: —")
        self._btn_logout.config(state="disabled", text="⏹ Encerrar Sessão")

    def _log(self, msg: str):
        self._lbl_log.config(text=f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def on_close(self):
        self._camera_ativa = False
        if self._cap:
            self._cap.release()
        if self._pose:
            self._pose.close()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = SmartGymApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()

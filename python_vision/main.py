import threading
import sqlite3
import serial
import serial.tools.list_ports
import cv2
import mediapipe as mp
import tkinter as tk
from tkinter import font as tkfont
from PIL import Image, ImageTk
from datetime import datetime
import os
import time
import numpy as np

# ── Configurações ────────────────────────────────────────────────────────────
SERIAL_PORT = "COM3"
BAUD_RATE = 9600
DB_PATH = os.path.join(os.path.dirname(__file__), "smart_gym.db")
CAMERA_INDEX = 0

# ── Cores (Tema Dark Gym) ────────────────────────────────────────────────────
COR_BG = "#0d0d0d"
COR_CARD = "#1a1a2e"
COR_PRIMARIA = "#e94560"
COR_TEXTO = "#eaeaea"
COR_CINZA = "#555555"
COR_VERDE = "#00e676"
COR_AMARELO = "#ffd600"

# ── MediaPipe Setup ──────────────────────────────────────────────────────────
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils
pose_model = mp_pose.Pose(
    model_complexity=1,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7
)


# ── Lógica de Movimento (Baseada no Aula_6) ──────────────────────────────────
class AnalisadorMovimento:
    def __init__(self):
        self.reset()

    def reset(self):
        self.count = 0
        self.estagio = None  # "down" (braço esticado) ou "up" (braço dobrado)
        self.angulo_atual = 0

    @staticmethod
    def calcular_angulo(a, b, c):
        """Calcula o ângulo entre ombro(a), cotovelo(b) e pulso(c)."""
        a = np.array(a)
        b = np.array(b)
        c = np.array(c)

        radianos = np.arctan2(c[1] - b[1], c[0] - b[0]) - np.arctan2(a[1] - b[1], a[0] - b[0])
        angulo = np.abs(radianos * 180.0 / np.pi)

        if angulo > 180.0:
            angulo = 360 - angulo
        return angulo

    def atualizar(self, landmarks):
        try:
            # Pegando pontos do lado direito (padrão do exercício)
            ombro = [landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value].x,
                     landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value].y]
            cotovelo = [landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW.value].x,
                        landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW.value].y]
            pulso = [landmarks[mp_pose.PoseLandmark.RIGHT_WRIST.value].x,
                     landmarks[mp_pose.PoseLandmark.RIGHT_WRIST.value].y]

            self.angulo_atual = self.calcular_angulo(ombro, cotovelo, pulso)

            # Lógica de contagem: Rosca Direta
            # Braço esticado (ângulo aberto)
            if self.angulo_atual > 150:
                self.estagio = "down"

            # Braço flexionado (ângulo fechado) + vindo do estado "down"
            if self.angulo_atual < 40 and self.estagio == "down":
                self.estagio = "up"
                self.count += 1
                return True
            return False
        except:
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
    conn = sqlite3.connect(DB_PATH);
    cur = conn.cursor()
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("INSERT INTO sessoes (aluno_id, uid_cartao, entrada) VALUES (?, ?, ?)", (aluno_id, uid, agora))
    sessao_id = cur.lastrowid
    conn.commit();
    conn.close()
    return sessao_id


def registrar_saida(sessao_id: int, rep_realizadas: int):
    conn = sqlite3.connect(DB_PATH);
    cur = conn.cursor()
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("UPDATE sessoes SET saida = ?, rep_realizadas = ? WHERE id = ?", (agora, rep_realizadas, sessao_id))
    conn.commit();
    conn.close()


# ── Aplicação Tkinter ─────────────────────────────────────────────────────────
class SmartGymApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Smart Gym — Estação Inteligente")
        self.root.configure(bg=COR_BG)
        self.root.geometry("900x600")
        self.root.resizable(False, False)

        self._aluno = None
        self._sessao_id = None
        self._camera_ativa = False
        self._cap = None
        self._serial = None
        self._analisador = AnalisadorMovimento()
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

        corpo = tk.Frame(self.root, bg=COR_BG)
        corpo.pack(fill="both", expand=True, padx=20, pady=15)

        # Painel Info (Esquerda)
        self._painel_info = tk.Frame(corpo, bg=COR_CARD, highlightthickness=1, highlightbackground=COR_CINZA)
        self._painel_info.pack(side="left", fill="both", expand=False, ipadx=15, ipady=15, padx=(0, 10))
        self._painel_info.config(width=280);
        self._painel_info.pack_propagate(False)

        self._lbl_status = tk.Label(self._painel_info, text="⏳ AGUARDANDO\nLOGIN", bg=COR_CARD, fg=COR_AMARELO,
                                    font=F(family="Helvetica", size=14, weight="bold"))
        self._lbl_status.pack(pady=(20, 10))

        tk.Frame(self._painel_info, bg=COR_CINZA, height=1).pack(fill="x", padx=10, pady=5)
        self._lbl_nome = tk.Label(self._painel_info, text="—", bg=COR_CARD, fg=COR_TEXTO,
                                  font=F(family="Helvetica", size=18, weight="bold"), wraplength=240)
        self._lbl_nome.pack(pady=(10, 5))

        self._lbl_exercicio = tk.Label(self._painel_info, text="", bg=COR_CARD, fg=COR_PRIMARIA,
                                       font=F(family="Helvetica", size=11))
        self._lbl_exercicio.pack()

        tk.Frame(self._painel_info, bg=COR_CINZA, height=1).pack(fill="x", padx=10, pady=12)
        tk.Label(self._painel_info, text="REPETIÇÕES", bg=COR_CARD, fg=COR_CINZA,
                 font=F(family="Helvetica", size=9, weight="bold")).pack()
        self._lbl_reps = tk.Label(self._painel_info, text="0", bg=COR_CARD, fg=COR_VERDE,
                                  font=F(family="Helvetica", size=54, weight="bold"))
        self._lbl_reps.pack()

        self._lbl_angulo = tk.Label(self._painel_info, text="Ângulo: 0°", bg=COR_CARD, fg=COR_AMARELO,
                                    font=F(family="Helvetica", size=10))
        self._lbl_angulo.pack()

        self._lbl_meta = tk.Label(self._painel_info, text="", bg=COR_CARD, fg=COR_CINZA,
                                  font=F(family="Helvetica", size=10))
        self._lbl_meta.pack()

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

        rodape = tk.Frame(self.root, bg="#111111", height=28)
        rodape.pack(fill="x", side="bottom")
        self._lbl_log = tk.Label(rodape, text="Sistema iniciado.", bg="#111111", fg=COR_CINZA,
                                 font=F(family="Helvetica", size=8))
        self._lbl_log.pack(side="left", padx=10, pady=4)

        self._atualizar_relogio()

    def _atualizar_relogio(self):
        self._lbl_hora.config(text=datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
        self.root.after(1000, self._atualizar_relogio)

    def _iniciar_serial(self):
        try:
            self._serial = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
        except:
            self._log("Modo Simulação (F5 p/ entrar)")
            self.root.bind("<F5>", lambda _: self._processar_uid("M3:N4:O5:P6"))

    def _iniciar_rfid_thread(self):
        def loop():
            while True:
                if self._serial and self._serial.is_open:
                    linha = self._serial.readline().decode().strip()
                    if linha and linha != "READY": self.root.after(0, self._processar_uid, linha)
                time.sleep(0.1)

        threading.Thread(target=loop, daemon=True).start()

    def _processar_uid(self, uid: str):
        if self._aluno: return
        aluno = buscar_aluno(uid)
        if aluno:
            self._sessao_id = registrar_entrada(aluno["id"], uid)
            self._aluno = aluno
            self._analisador.reset()
            self._lbl_status.config(text="✅ TREINO\nATIVO", fg=COR_VERDE)
            self._lbl_nome.config(text=f"Bem-vindo,\n{aluno['nome'].split()[0]}!")
            self._lbl_exercicio.config(text=f"🏋 {aluno['exercicio']}")
            self._lbl_meta.config(text=f"/ {aluno['repeticoes']} meta")
            self._btn_logout.config(state="normal")
            
            # Feedback para o Arduino
            if self._serial and self._serial.is_open:
                self._serial.write(b"OK\n")
                
            self._iniciar_camera()
            self._log(f"Login: {aluno['nome']}")
        else:
            # Aluno não encontrado
            if self._serial and self._serial.is_open:
                self._serial.write(b"DENY\n")
            self._log(f"Cartão desconhecido: {uid}")

    def _iniciar_camera(self):
        self._camera_ativa = True
        self._cap = cv2.VideoCapture(CAMERA_INDEX)
        self._lbl_cam_placeholder.place_forget()
        self._atualizar_frame_camera()

    def _atualizar_frame_camera(self):
        # 1. Verifica se a câmera ainda deve estar ativa
        if not self._camera_ativa or self._cap is None:
            return

        ret, frame = self._cap.read()
        if ret:
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = pose_model.process(rgb)

            if res.pose_landmarks:
                mp_drawing.draw_landmarks(frame, res.pose_landmarks, mp_pose.POSE_CONNECTIONS)

                # Tenta atualizar a contagem
                if self._analisador.atualizar(res.pose_landmarks.landmark):
                    self._lbl_reps.config(text=str(self._analisador.count))  # Atualiza logo o número
                    self._log(f"Repetição {self._analisador.count}")

                    # ─── LÓGICA DE META BATIDA ───
                    meta = int(self._aluno['repeticoes'])
                    if self._analisador.count >= meta:
                        self._log(f"Meta de {meta} batida! Parabéns!")
                        # Para a câmera, mas NÃO limpa o painel do aluno ainda
                        self.root.after(500, self._parar_camera_automaticamente)
                        return

                # Atualiza a interface
                self._lbl_reps.config(text=str(self._analisador.count))
                self._lbl_angulo.config(text=f"Ângulo: {int(self._analisador.angulo_atual)}°")

            # Renderização do Frame no Canvas
            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            cw, ch = self._canvas_cam.winfo_width(), self._canvas_cam.winfo_height()
            if cw > 1:
                img = img.resize((cw, ch), Image.Resampling.LANCZOS)
            self._img_tk = ImageTk.PhotoImage(image=img)
            self._canvas_cam.create_image(0, 0, anchor="nw", image=self._img_tk)

        # Agenda o próximo frame
        self.root.after(10, self._atualizar_frame_camera)

    def _encerrar_sessao(self):
        if self._sessao_id: registrar_saida(self._sessao_id, self._analisador.count)
        self._camera_ativa = False
        if self._cap: self._cap.release()
        self._aluno = None
        self._canvas_cam.delete("all")
        self._lbl_cam_placeholder.place(relx=0.5, rely=0.5, anchor="center")
        self._lbl_status.config(text="⏳ AGUARDANDO\nLOGIN", fg=COR_AMARELO)
        self._lbl_nome.config(text="—")
        self._lbl_reps.config(text="0")
        self._lbl_meta.config(text="")
        self._lbl_exercicio.config(text="")
        self._btn_logout.config(state="disabled")

    def _parar_camera_automaticamente(self):
        """Para o vídeo ao bater a meta, mas mantém o botão de encerrar ativo."""
        self._camera_ativa = False
        if self._cap:
            self._cap.release()
            self._cap = None

        # Limpa o vídeo e volta o placeholder
        self._canvas_cam.delete("all")
        self._lbl_cam_placeholder.place(relx=0.5, rely=0.5, anchor="center")

        # Garante que o status mostre que acabou e o botão continue ativo
        self._lbl_status.config(text="🏆 META\nCONCLUÍDA", fg=COR_VERDE)
        self._btn_logout.config(state="normal", text="⏹ Finalizar e Salvar")
        self._log("Treino concluído. Clique em Finalizar para salvar.")

    def _encerrar_sessao(self):
        """Chamado pelo botão ou ao trocar de aluno. Salva no DB e limpa tudo."""
        with self._lock:
            aluno = self._aluno
            sessao_id = self._sessao_id
            reps = self._analisador.count
            self._aluno = None
            self._sessao_id = None

        if sessao_id:
            registrar_saida(sessao_id, reps)
            self._log(f"Dados salvos: {reps} reps.")

        # Desliga câmera se ainda estiver aberta
        self._camera_ativa = False
        if self._cap:
            self._cap.release()
            self._cap = None

        # Reset Total da UI para o próximo
        self._canvas_cam.delete("all")
        self._lbl_cam_placeholder.place(relx=0.5, rely=0.5, anchor="center")
        self._lbl_status.config(text="⏳ AGUARDANDO\nLOGIN", fg=COR_AMARELO)
        self._lbl_nome.config(text="—")
        self._lbl_exercicio.config(text="")
        self._lbl_reps.config(text="0")
        self._lbl_meta.config(text="")
        self._lbl_angulo.config(text="Ângulo: 0°")
        self._btn_logout.config(state="disabled", text="⏹ Encerrar Sessão")
    def _log(self, msg: str):
        self._lbl_log.config(text=f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def on_close(self):
        self._camera_ativa = False
        if self._cap: self._cap.release()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = SmartGymApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
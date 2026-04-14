import serial
import time
import cv2
import mediapipe as mp
import math  # Importação necessária para calcular os ângulos


# ==========================================
# FUNÇÃO MATEMÁTICA PARA CALCULAR ÂNGULOS
# ==========================================
def calcular_angulo(a, b, c):
    """
    Calcula o ângulo entre três pontos.
    a = Primeiro ponto (ex: Ombro)
    b = Ponto central (ex: Cotovelo)
    c = Terceiro ponto (ex: Pulso)
    """
    radianos = math.atan2(c[1] - b[1], c[0] - b[0]) - math.atan2(a[1] - b[1], a[0] - b[0])
    angulo = abs(radianos * 180.0 / math.pi)

    if angulo > 180.0:
        angulo = 360 - angulo

    return angulo


# ==========================================
# CONFIGURAÇÃO DA PORTA SERIAL
# ==========================================
PORTA_SERIAL = 'COM12'
BAUD_RATE = 9600

try:
    print(f"Tentando conectar na porta {PORTA_SERIAL}...")
    arduino = serial.Serial(PORTA_SERIAL, BAUD_RATE, timeout=1)
    time.sleep(2)
    print("Conectado ao Arduino com sucesso!")
except Exception as e:
    print(f"Erro ao conectar na porta serial: {e}")
    print("Verifique se o Arduino está conectado e se a porta COM está correta.")
    exit()

# ==========================================
# CONFIGURAÇÃO DO MEDIAPIPE TASKS (NOVA API)
# ==========================================
MODEL_PATH = 'pose_landmarker_full.task'  # Certifique-se de que este arquivo está na mesma pasta!

BaseOptions = mp.tasks.BaseOptions
PoseLandmarker = mp.tasks.vision.PoseLandmarker
PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

options = PoseLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=MODEL_PATH),
    running_mode=VisionRunningMode.VIDEO,
    min_pose_detection_confidence=0.5,
    min_pose_presence_confidence=0.5,
    min_tracking_confidence=0.5
)

landmarker = PoseLandmarker.create_from_options(options)

CUSTOM_POSE_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 7), (0, 4), (4, 5), (5, 6), (6, 8), (9, 10),
    (11, 12), (11, 13), (13, 15), (15, 17), (15, 19), (15, 21), (17, 19),
    (12, 14), (14, 16), (16, 18), (16, 20), (16, 22), (18, 20),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (27, 29), (29, 31), (31, 27),
    (24, 26), (26, 28), (28, 30), (30, 32), (32, 28)
]

# Variáveis de controle de estado do Sistema e do Exercício
aluno_identificado = False
id_aluno = ""

contador_reps = 0
estagio_movimento = None  # Pode ser "descendo" ou "subindo"

# ==========================================
# INÍCIO DO LOOP PRINCIPAL ÚNICO
# ==========================================
print("Abrindo a câmera...")
cap = cv2.VideoCapture(0)
start_time = time.time()

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        print("Erro ao acessar a câmera.")
        break

    image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image_bgr = frame.copy()

    # ---------------------------------------------------------
    # ESTADO 1: AGUARDANDO CARTÃO
    # ---------------------------------------------------------
    if not aluno_identificado:
        try:
            if arduino.in_waiting > 0:
                linha = arduino.readline().decode('utf-8', errors='ignore').strip()

                if linha.startswith("UID:"):
                    id_aluno = linha.replace("UID:", "").strip()
                    print(f"\n[ACESSO LIBERADO] Aluno ID: {id_aluno}")
                    print("Iniciando monitoramento de postura...")

                    aluno_identificado = True
                    start_time = time.time()
        except Exception as e:
            print(f"Erro na leitura serial: {e}")

        cv2.putText(image_bgr, 'Smart Gym - Catraca Bloqueada', (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 165, 255), 2, cv2.LINE_AA)
        cv2.putText(image_bgr, 'Aproxime seu cartao RFID no leitor...', (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)

    # ---------------------------------------------------------
    # ESTADO 2: ALUNO LIBERADO (Processa o MediaPipe e Conta)
    # ---------------------------------------------------------
    else:
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb)
        frame_timestamp_ms = int((time.time() - start_time) * 1000)

        detection_result = landmarker.detect_for_video(mp_image, frame_timestamp_ms)

        if detection_result.pose_landmarks:
            h, w, _ = image_bgr.shape

            for pose_landmarks in detection_result.pose_landmarks:
                # 1. Desenha o esqueleto
                for connection in CUSTOM_POSE_CONNECTIONS:
                    start_idx, end_idx = connection
                    start_landmark = pose_landmarks[start_idx]
                    end_landmark = pose_landmarks[end_idx]
                    start_point = (int(start_landmark.x * w), int(start_landmark.y * h))
                    end_point = (int(end_landmark.x * w), int(end_landmark.y * h))
                    cv2.line(image_bgr, start_point, end_point, (245, 66, 230), 2)

                for landmark in pose_landmarks:
                    cx, cy = int(landmark.x * w), int(landmark.y * h)
                    cv2.circle(image_bgr, (cx, cy), 4, (245, 117, 66), cv2.FILLED)

                # 2. LÓGICA DE CONTAGEM (Exemplo: Rosca Direta - Braço Esquerdo)
                # Pegando as coordenadas x, y do Ombro (11), Cotovelo (13) e Pulso (15)
                ombro = [pose_landmarks[11].x, pose_landmarks[11].y]
                cotovelo = [pose_landmarks[13].x, pose_landmarks[13].y]
                pulso = [pose_landmarks[15].x, pose_landmarks[15].y]

                # Calcula o ângulo do cotovelo
                angulo = calcular_angulo(ombro, cotovelo, pulso)

                # Exibe o ângulo perto do cotovelo para debug visual
                cv2.putText(image_bgr, str(int(angulo)),
                            (int(cotovelo[0] * w), int(cotovelo[1] * h) - 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2, cv2.LINE_AA)

                # Máquina de estados: Braço esticado (> 160 graus) -> Braço dobrado (< 30 graus)
                if angulo > 160:
                    estagio_movimento = "descendo"
                if angulo < 30 and estagio_movimento == 'descendo':
                    estagio_movimento = "subindo"
                    contador_reps += 1
                    print(f"Repetições: {contador_reps}")

        # Interface (HUD) de treino liberado e Caixa do Contador
        cv2.putText(image_bgr, f'Acesso Liberado - ID: {id_aluno}', (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA)
        cv2.putText(image_bgr, 'Pressione "Q" para encerrar o treino', (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

        # Desenha uma caixa bonita para o contador na tela
        cv2.rectangle(image_bgr, (10, 80), (250, 160), (245, 117, 16), -1)  # Fundo laranja
        cv2.putText(image_bgr, 'REPETICOES', (25, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2, cv2.LINE_AA)
        cv2.putText(image_bgr, str(contador_reps), (25, 150), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3,
                    cv2.LINE_AA)

        cv2.putText(image_bgr, 'FASE', (140, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2, cv2.LINE_AA)
        cv2.putText(image_bgr, str(estagio_movimento) if estagio_movimento else "-", (140, 140),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)

    # ---------------------------------------------------------
    # EXIBE A TELA FINAL E CHECA O BOTÃO SAIR
    # ---------------------------------------------------------
    cv2.imshow('Smart Gym - Visao Computacional', image_bgr)

    if cv2.waitKey(10) & 0xFF == ord('q'):
        break

arduino.close()
cap.release()
cv2.destroyAllWindows()
print("Sistema encerrado com sucesso.")

import serial
import time
import cv2
import mediapipe as mp

# ==========================================
# CONFIGURAÇÃO DA PORTA SERIAL
# ==========================================
# IMPORTANTE: Altere 'COM3' para a porta correta do seu Arduino (No Linux/Mac costuma ser '/dev/ttyACM0' ou similar)
PORTA_SERIAL = 'COM3' 
BAUD_RATE = 9600

try:
    print(f"Tentando conectar na porta {PORTA_SERIAL}...")
    arduino = serial.Serial(PORTA_SERIAL, BAUD_RATE, timeout=1)
    time.sleep(2) # Tempo para estabilizar a conexão
    print("Conectado com sucesso! Aguardando o cartão do aluno na catraca...")
except Exception as e:
    print(f"Erro ao conectar na porta serial: {e}")
    print("Verifique se o Arduino está conectado e se a porta COM está correta.")
    exit()

# ==========================================
# CONFIGURAÇÃO DO MEDIAPIPE (VISÃO COMPUTACIONAL)
# ==========================================
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils
pose = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)

aluno_identificado = False
id_aluno = ""

# 1. LOOP DE ESPERA DO CARTÃO (Integração Hardware -> Software)
while not aluno_identificado:
    if arduino.in_waiting > 0:
        # Lê a linha enviada pelo Arduino, decodifica e remove espaços em branco
        id_aluno = arduino.readline().decode('utf-8').strip()
        
        if id_aluno:
            print(f"\n[ACESSO LIBERADO] Aluno ID: {id_aluno}")
            print("Iniciando monitoramento de postura...")
            aluno_identificado = True

arduino.close() # Libera a porta serial após a leitura

# 2. LOOP DE CAPTURA BIOMÉTRICA (MediaPipe)
if aluno_identificado:
    cap = cv2.VideoCapture(0) # 0 é geralmente a webcam padrão

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            print("Erro ao acessar a câmera.")
            break

        # O MediaPipe trabalha com imagens em RGB, o OpenCV usa BGR por padrão
        image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image_rgb.flags.writeable = False
        
        # Processa a imagem e detecta os landmarks do corpo
        results = pose.process(image_rgb)
        
        # Reverte para BGR para exibir na tela do OpenCV
        image_rgb.flags.writeable = True
        image_bgr = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)

        # Desenha as marcações das articulações no corpo do aluno
        if results.pose_landmarks:
            mp_drawing.draw_landmarks(
                image_bgr, 
                results.pose_landmarks, 
                mp_pose.POSE_CONNECTIONS,
                mp_drawing.DrawingSpec(color=(245,117,66), thickness=2, circle_radius=2), # Cor dos pontos
                mp_drawing.DrawingSpec(color=(245,66,230), thickness=2, circle_radius=2)  # Cor das linhas
            )

        # Coloca o ID do aluno na tela como HUD
        cv2.putText(image_bgr, f'Smart Gym - Aluno ID: {id_aluno}', (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA)
        cv2.putText(image_bgr, 'Pressione "Q" para encerrar o treino', (10, 60), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

        # Mostra o resultado na tela
        cv2.imshow('Smart Gym - Monitoramento de Execucao', image_bgr)

        # Encerra o programa se apertar a tecla 'q'
        if cv2.waitKey(10) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("Treino finalizado com sucesso.")
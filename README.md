# 🏋️‍♂️ Smart Gym - Ecossistema de Estações Inteligentes

## Descrição do Projeto
O caso da Smart Gym propõe a evolução do treino digital. O objetivo deste projeto é desenvolver um protótipo de sistema de monitoramento inteligente para as *Smart Stations*. O sistema é capaz de replicar a atenção de um personal trainer através de duas etapas principais:
1. **Identificação e Contexto (RFID):** Autenticação do aluno via cartão físico para carregamento de perfil, visando a personalização do treino.
2. **Captura Biométrica (Visão Computacional):** Ativação da câmera após o login para monitorar a amplitude de movimento e postura do aluno em tempo real, utilizando mapeamento de articulações corporais (landmarks) para garantir a execução com técnica perfeita.

## Equipe
* Gabriel Danius - RM 556747
* Carlos Eduardo - RM 556785
* Caio Rossini - RM 555084
* Giulia Rocha - RM 558084

## Hardware e Componentes Utilizados
* 1x Placa Microcontroladora (Arduino Uno ou ESP32)
* 1x Módulo Leitor RFID RC522
* 1x Cartão/Tag RFID 13.56MHz
* Jumpers variados para conexão via protocolo SPI
* 1x Webcam (integrada ou USB) para o monitoramento

## Bibliotecas Utilizadas
* **Arduino/C++:**
  * `SPI.h`: Para comunicação síncrona com o módulo leitor.
  * `MFRC522.h`: Para abstração dos comandos de leitura do protocolo da tag RFID.
* **Python:**
  * `pyserial`: Para estabelecer a comunicação serial entre o PC e o Microcontrolador.
  * `opencv-python (cv2)`: Para manipulação de janelas, acesso à webcam e processamento de imagens.
  * `mediapipe`: Framework do Google utilizado para extrair as coordenadas das articulações (Pose Estimation).

## Instruções de Reprodução e Setup

### 1. Configuração do Hardware (Arduino)
1. Conecte o módulo RFID RC522 ao Arduino seguindo a pinagem do barramento SPI (MISO, MOSI, SCK, SDA/SS e RST).
2. Abra a IDE do Arduino, vá em `Gerenciador de Bibliotecas` e instale a biblioteca **MFRC522** (por GithubCommunity).
3. Faça o upload do código localizado na pasta `arduino_rfid` para a sua placa.

### 2. Configuração do Software (Python)
1. Certifique-se de ter o Python 3 instalado na sua máquina.
2. Abra o terminal na pasta do projeto e instale as dependências executando o comando:
   ```bash
   pip install pyserial opencv-python mediapipe

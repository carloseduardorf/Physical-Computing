# 🏋️‍♂️ Smart Gym - Ecossistema de Estações Inteligentes

## Descrição do Projeto
O caso da Smart Gym propõe a evolução do treino digital. O objetivo deste projeto é desenvolver um protótipo de sistema de monitoramento inteligente para as *Smart Stations*. O sistema é capaz de replicar a atenção de um personal trainer através de duas etapas principais:

1. **Identificação e Contexto (RFID):** Autenticação do aluno via cartão físico para carregamento de perfil, visando a personalização do treino.
2. **Captura Biométrica (Visão Computacional):** Ativação da câmera após a identificação do aluno para monitorar a amplitude de movimento e postura do aluno em tempo real, utilizando mapeamento de articulações corporais (landmarks) para garantir a execução com técnica perfeita.

## Equipe
* Carlos Eduardo - RM: 556785
* Gabriel Danius - RM: 555747
* Caio Rossini - RM: 555084
* Giulia Rocha - RM: 558084

## Hardware e Componentes Utilizados
* 1x Placa Microcontroladora (Arduino Uno)
* 1x Módulo Leitor RFID RC522
* 1x Cartão/Tag RFID 13.56MHz
* 7 jumpers macho-fêmea para realizar conexão via protocolo SPI
* 1x Webcam (integrada ou USB) para o monitoramento

## Bibliotecas Utilizadas

**Arduino/C++:**
* `SPI.h`: Para comunicação síncrona com o módulo leitor.
* `MFRC522.h`: Para abstração dos comandos de leitura do protocolo da tag RFID.

**Python:**
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

### 3. Print do projeto montado no Wokwi
<img width="616" height="480" alt="image" src="https://github.com/user-attachments/assets/c1095f81-abc4-4d49-8ae0-cdd640ab3bd4" />

Imagem do projeto Wokwi (https://wokwi.com/projects/461231531669227521)

## Link Video Demonstrativo
[Link video demonstrativo](https://drive.google.com/file/d/1WIEtccEw9Mt0iQGq0snGRgkALArE9-nA/view?usp=sharing)

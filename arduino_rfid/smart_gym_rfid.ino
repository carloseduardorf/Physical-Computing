/*
 * Smart Gym - CP02
 * Leitura de cartão RFID RC522 e envio do UID via Serial
 * Placa: Arduino Uno
 * Autor: Equipe Smart Gym
 */

#include <SPI.h>
#include <MFRC522.h>

// ── Pinos ──────────────────────────────────────────────────────────────────
#define SS_PIN   10
#define RST_PIN   9
#define LED_GREEN  7   // LED verde  → acesso autorizado
#define LED_RED    6   // LED vermelho → acesso negado / aguardando
#define BUZZER     5   // Buzzer (ativo)

// ── Objetos ────────────────────────────────────────────────────────────────
MFRC522 mfrc522(SS_PIN, RST_PIN);

// ── Setup ──────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(9600);
  SPI.begin();
  mfrc522.PCD_Init();

  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_RED,   OUTPUT);
  pinMode(BUZZER,    OUTPUT);

  // Estado inicial: aguardando
  digitalWrite(LED_RED,   HIGH);
  digitalWrite(LED_GREEN, LOW);
  digitalWrite(BUZZER,    LOW);

  Serial.println("READY");  // sinal para o Python saber que o Arduino está pronto
}

// ── Loop ───────────────────────────────────────────────────────────────────
void loop() {

  // Verifica se o Python enviou feedback ("OK" ou "DENY") via Serial
  if (Serial.available() > 0) {
    String feedback = Serial.readStringUntil('\n');
    feedback.trim();

    if (feedback == "OK") {
      // Aluno reconhecido: verde + beep curto
      digitalWrite(LED_RED,   LOW);
      digitalWrite(LED_GREEN, HIGH);
      tone(BUZZER, 1000, 150);
      delay(200);
      noTone(BUZZER);

    } else if (feedback == "DENY") {
      // UID desconhecido: vermelho + beep longo
      digitalWrite(LED_GREEN, LOW);
      digitalWrite(LED_RED,   HIGH);
      tone(BUZZER, 400, 600);
      delay(700);
      noTone(BUZZER);

    } else if (feedback == "LOGOUT") {
      // Sessão encerrada: volta ao vermelho
      digitalWrite(LED_GREEN, LOW);
      digitalWrite(LED_RED,   HIGH);
    }
  }

  // Aguarda novo cartão
  if (!mfrc522.PICC_IsNewCardPresent() || !mfrc522.PICC_ReadCardSerial()) {
    return;
  }

  // Monta string do UID em hex separado por ":"
  String uid = "";
  for (byte i = 0; i < mfrc522.uid.size; i++) {
    if (mfrc522.uid.uidByte[i] < 0x10) uid += "0";
    uid += String(mfrc522.uid.uidByte[i], HEX);
    if (i < mfrc522.uid.size - 1) uid += ":";
  }
  uid.toUpperCase();

  Serial.println(uid);  // envia para o Python

  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();

  delay(1500);  // debounce: evita leitura duplicada
}

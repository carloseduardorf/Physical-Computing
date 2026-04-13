#include <SPI.h>
#include <MFRC522.h>

// Definição dos pinos (Padrão para Arduino Uno. Se usar ESP32, ajuste para SS=5 e RST=22, por exemplo)
#define SS_PIN 10
#define RST_PIN 9

// Instancia o objeto RFID
MFRC522 rfid(SS_PIN, RST_PIN);

void setup() {
  Serial.begin(9600); // Inicia a comunicação serial com o PC
  SPI.begin();        // Inicia o barramento SPI
  rfid.PCD_Init();    // Inicia o módulo MFRC522
  Serial.println("Aguardando aproximacao do cartao RFID do aluno...");
}

void loop() {
  // Verifica se há um novo cartão presente
  if (!rfid.PICC_IsNewCardPresent()) {
    return;
  }
  
  // Verifica se consegue ler o cartão
  if (!rfid.PICC_ReadCardSerial()) {
    return;
  }

  // Monta a string com o UID (ID único do cartão)
  String content = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    content.concat(String(rfid.uid.uidByte[i] < 0x10 ? " 0" : " "));
    content.concat(String(rfid.uid.uidByte[i], HEX));
  }
  
  content.toUpperCase();
  
  // Envia o ID limpo via Serial para o Python ler
  Serial.println(content.substring(1));
  
  // Dá um pequeno delay para não ler múltiplas vezes o mesmo toque
  delay(2000); 
}
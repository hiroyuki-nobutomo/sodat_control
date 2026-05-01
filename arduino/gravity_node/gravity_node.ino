/**
 * Arduino UNO R4 Conductivity Node (Pull Model)
 * 
 * Target: Arduino UNO R4 Minima
 * Sensor: DFRobot Gravity Analog Electrical Conductivity Sensor
 * Port: Analog Pin A1
 * Output: JSON via Serial (9600 baud)
 * 
 * Logic: Waits for the character 'R' over Serial before taking 
 * a measurement. This prevents probe polarization and ensures
 * data is only collected when requested by the Pi.
 */

#include <Arduino.h>

// --- Configuration ---
const int EC_PIN = A1;           // Sensor connected to Analog A1
const float VREF = 5.0;          // Reference voltage (5.0V for UNO R4 with 5V jumper)
const int SAMPLE_COUNT = 30;     // Number of readings to average

void takeMeasurement() {
  // 1. Collect and Average Analog Readings
  long analogSum = 0;
  for (int i = 0; i < SAMPLE_COUNT; i++) {
    analogSum += analogRead(EC_PIN);
    delay(10);
  }
  float analogAverage = (float)analogSum / (float)SAMPLE_COUNT;

  // 2. Convert to Voltage
  float voltage = analogAverage * VREF / 1024.0;

  // 3. Output RAW VOLTAGE as JSON
  Serial.print("{\"voltage_v\": ");
  Serial.print(voltage, 3);
  Serial.println("}");
}

void setup() {
  Serial.begin(9600);
  pinMode(EC_PIN, INPUT);
  
  // Give the serial port time to initialize
  delay(1000);
}

void loop() {
  // Wait for command from Raspberry Pi
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    
    // 'R' = Read command
    if (cmd == 'R') {
      // CRITICAL: Clear the serial buffer of any garbage noise
      while(Serial.available() > 0) Serial.read();
      takeMeasurement();
    }
  }
  
  // Small delay to prevent CPU spinning
  delay(100);
}

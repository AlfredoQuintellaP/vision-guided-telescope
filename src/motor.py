"""
motor.py — Driver para motor de passo 28BYJ-48 com ULN2003
Raspberry Pi 4 — pinos conforme ligação do projeto:

    GPIO 2  → IN1
    GPIO 3  → IN2
    GPIO 14 → IN3
    GPIO 22 → IN4

O 28BYJ-48 usa sequência de meia-passo (8 passos) para maior
precisão e torque suave. Com a redução interna de ~64:1 e
8 passos por ciclo, são necessários 4096 meios-passos para
uma rotação completa do eixo de saída.

Uso básico:
    motor = StepperMotor()
    motor.step(200)          # 200 passos no sentido horário
    motor.step(-200)         # 200 passos no sentido anti-horário
    motor.rotate_degrees(90) # roda 90°
    motor.release()          # desliga as bobines (evita aquecimento)
"""

import time
import RPi.GPIO as GPIO  # type: ignore


# ---------------------------------------------------------------------------
# Sequência de meia-passo para 28BYJ-48
# Ordem das colunas: IN1, IN2, IN3, IN4
# ---------------------------------------------------------------------------
HALF_STEP_SEQUENCE = [
    [1, 0, 0, 0],
    [1, 1, 0, 0],
    [0, 1, 0, 0],
    [0, 1, 1, 0],
    [0, 0, 1, 0],
    [0, 0, 1, 1],
    [0, 0, 0, 1],
    [1, 0, 0, 1],
]

# Passos de meia-passo por volta completa do eixo de saída
# Motor: 8 meios-passos × 64 (redução interna) = 512
# Com a redução extra (~8:1) da caixa: 512 × 8 = 4096
# Valor real medido para o 28BYJ-48 padrão:
STEPS_PER_REVOLUTION = 4096


class StepperMotor:

    def __init__(
        self,
        pin_in1: int = 2,
        pin_in2: int = 3,
        pin_in3: int = 14,
        pin_in4: int = 22,
        step_delay: float = 0.001,  # segundos entre meios-passos (1 ms)
    ):
        """
        pin_in1..in4  : pinos GPIO (BCM) ligados ao ULN2003
        step_delay    : tempo entre passos — menor = mais rápido, mas pode perder passos
                        mínimo estável para o 28BYJ-48: ~0.001 s (1 ms)
        """
        self._pins = [pin_in1, pin_in2, pin_in3, pin_in4]
        self._step_delay = step_delay
        self._current_step = 0   # índice na sequência
        self._position = 0       # posição acumulada em meios-passos

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for pin in self._pins:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, 0)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def step(self, n: int):
        """
        Avança n meios-passos.
        n > 0 → sentido horário
        n < 0 → sentido anti-horário
        """
        direction = 1 if n >= 0 else -1
        for _ in range(abs(n)):
            self._current_step = (self._current_step + direction) % len(HALF_STEP_SEQUENCE)
            self._apply_step(self._current_step)
            self._position += direction
            time.sleep(self._step_delay)

    def rotate_degrees(self, degrees: float):
        """
        Roda o eixo de saída pelo número de graus indicado.
        degrees > 0 → horário
        degrees < 0 → anti-horário
        """
        n = int(STEPS_PER_REVOLUTION * degrees / 360)
        self.step(n)

    def rotate_revolutions(self, revolutions: float):
        """Roda N voltas completas (pode ser decimal)."""
        n = int(STEPS_PER_REVOLUTION * revolutions)
        self.step(n)

    def release(self):
        """Desliga todas as bobines. Chame sempre ao terminar para não aquecer."""
        for pin in self._pins:
            GPIO.output(pin, 0)

    def cleanup(self):
        """Libera os GPIO. Chame no final do programa."""
        self.release()
        GPIO.cleanup()

    @property
    def position(self) -> int:
        """Posição acumulada em meios-passos desde o início."""
        return self._position

    @property
    def position_degrees(self) -> float:
        """Posição acumulada convertida em graus."""
        return self._position * 360 / STEPS_PER_REVOLUTION

    # ------------------------------------------------------------------
    # Interno
    # ------------------------------------------------------------------

    def _apply_step(self, step_index: int):
        seq = HALF_STEP_SEQUENCE[step_index]
        for pin, val in zip(self._pins, seq):
            GPIO.output(pin, val)

    # Context manager para usar com `with`
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.cleanup()


# ---------------------------------------------------------------------------
# Teste direto: python motor.py
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Teste do motor 28BYJ-48")
    print("Pinos: IN1=GPIO2  IN2=GPIO3  IN3=GPIO14  IN4=GPIO22")
    print()

    with StepperMotor() as motor:
        print("→ 1 volta horária...")
        motor.rotate_revolutions(1)
        motor.release()
        time.sleep(0.5)

        print("→ 1 volta anti-horária...")
        motor.rotate_revolutions(-1)
        motor.release()
        time.sleep(0.5)

        print("→ 90° horário...")
        motor.rotate_degrees(90)
        motor.release()
        time.sleep(0.5)

        print("→ 90° anti-horário...")
        motor.rotate_degrees(-90)
        motor.release()

        print(f"\nPosição final: {motor.position_degrees:.1f}°")
        print("Concluído.")

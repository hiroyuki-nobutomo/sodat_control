import logging
import time
try:
    from gpiozero import LED
    HAS_GPIO = True
except (ImportError, Exception):
    # Exception can happen if no pin factory is available (e.g. on Mac)
    HAS_GPIO = False
    logging.warning("gpiozero not available or failed. Using Mock LED.")

class MockLED:
    def __init__(self, pin):
        self.pin = pin
    def on(self): pass
    def off(self): pass
    def blink(self, on_time=1, off_time=1, n=None, background=True): pass

class StatusIndicator:
    def __init__(self, pin: int = 4):
        self.pin = pin
        if HAS_GPIO:
            try:
                self.led = LED(pin)
            except Exception as e:
                logging.warning(f"Failed to initialize LED on pin {pin}: {e}")
                self.led = MockLED(pin)
        else:
            self.led = MockLED(pin)

    def signal_boot(self):
        """Blinks slowly to indicate booting/idle."""
        # background=True is default
        self.led.blink(on_time=1, off_time=1)

    def signal_success(self):
        """Pulses once to indicate success."""
        # Blink once, non-background (blocking) for immediate feedback?
        # Actually, for "upload success", a quick blip is good.
        # If we use background=False, it blocks the thread.
        # But blink(n=1) might leave it off.
        # Let's turn it on briefly.
        self.led.blink(on_time=0.2, off_time=0.2, n=1, background=False)
        # Return to heartbeat? Or stay off?
        # Typically we want to return to "Idle" state.
        # But this class is simple. The caller should restore state if needed.
        # For now, let's just blink.

    def signal_error(self):
        """Blinks rapidly to indicate error."""
        self.led.blink(on_time=0.1, off_time=0.1)

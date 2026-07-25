import app
from app_components.menu import Menu
from app_components.background import Background as bg
from events.input import BUTTON_TYPES, ButtonDownEvent
from system.eventbus import eventbus
from system.patterndisplay.events import PatternDisable, PatternEnable


class PowerApp(app.App):
    def __init__(self):
        super().__init__()
        # state: "menu", "poweroff", "standby"
        self.state = "menu"
        self.screen_blank = False
        self._prev_blank = False
        self._force_render = False
        self._ignore_next_button = False
        self._standby_refresh_elapsed_ms = 0
        self._standby_refresh_interval_ms = 1000
        self.menu = self._build_menu()

    def _build_menu(self):
        return Menu(
            self,
            ["Standby", "Power Off"],
            select_handler=self._menu_select,
            back_handler=self._menu_back,
        )

    def _set_hexpansion_low_power(self):
        from egpio import ePin

        HEXPANSION_POWER = {
            (2, 12),
            (2, 13),
            (1, 8),
            (1, 9),
            (1, 10),
            (1, 11),
        }

        for epin in HEXPANSION_POWER:
            pin = ePin(epin, ePin.OUT)
            pin.on()
        pin = ePin((2, 2), ePin.OUT)
        pin.off()

    def _restore_standby_hardware(self):
        from egpio import ePin
        from tildagonos import (
            tildagonos,
            EPIN_ND_A,
            EPIN_ND_B,
            EPIN_ND_C,
            EPIN_ND_D,
            EPIN_ND_E,
            EPIN_ND_F,
        )

        for nd_pin in (
            EPIN_ND_A,
            EPIN_ND_B,
            EPIN_ND_C,
            EPIN_ND_D,
            EPIN_ND_E,
            EPIN_ND_F,
        ):
            ePin(nd_pin, ePin.IN)
        tildagonos.set_led_power(True)

    def _get_standby_power_lines(self):
        try:
            import power

            battery_pct = power.BatteryLevel()
            charge_current_ma = power.Icharge() * 1000.0
            charge_state = power.BatteryChargeState()
            return (
                f"Battery: {battery_pct:.0f}%",
                f"Charge Current: {charge_current_ma:.0f} mA",
                f"State: {charge_state}",
            )
        except Exception:
            return ("Battery: n/a", "Charge Current: n/a", "State: n/a")

    def _menu_select(self, item, _idx):
        self.menu._cleanup()
        if item == "Power Off":
            import power

            power.Off()
            self.state = "poweroff"
            self._force_render = True
            self._ignore_next_button = True
            self._set_hexpansion_low_power()
        else:
            self.state = "standby"
            self._force_render = True
            self._ignore_next_button = True
            self._standby_refresh_elapsed_ms = 0
            eventbus.emit(PatternDisable())
            self._set_hexpansion_low_power()
        eventbus.on_async(ButtonDownEvent, self._handle_buttondown, self)

    def _menu_back(self):
        self.menu._cleanup()
        self.minimise()

    async def _handle_buttondown(self, event: ButtonDownEvent):
        if self._ignore_next_button:
            self._ignore_next_button = False
            return
        if self.state == "standby" and (
            BUTTON_TYPES["CANCEL"] in event.button
            or BUTTON_TYPES["LEFT"] in event.button
        ):
            eventbus.remove(ButtonDownEvent, self._handle_buttondown, self)
            eventbus.emit(PatternEnable())
            self._restore_standby_hardware()
            self.state = "menu"
            self.screen_blank = False
            self._prev_blank = False
            self._standby_refresh_elapsed_ms = 0
            self.menu = self._build_menu()
            self.terminate()
            return
        name = event.button.name
        if (
            name in ("LEFTPROX", "RIGHTPROX")
            or name.startswith("TOUCH")
            or name.startswith("JOY")
        ):
            return
        print(f"PowerOff: button pressed: {event.button}")
        self.screen_blank = not self.screen_blank

    def update(self, delta):
        if self.state == "menu":
            self.menu.update(delta)
            return True
        # In poweroff/standby: only re-render when screen_blank changes
        if self._force_render:
            self._force_render = False
            return True
        if self._prev_blank != self.screen_blank:
            self._prev_blank = self.screen_blank
            return True
        if self.state == "standby" and not self.screen_blank:
            self._standby_refresh_elapsed_ms += delta
            if self._standby_refresh_elapsed_ms >= self._standby_refresh_interval_ms:
                self._standby_refresh_elapsed_ms = 0
                return True
        return False

    def draw(self, ctx):
        ctx.save()
        if self.state == "menu":
            bg.draw(ctx)
            self.menu.draw(ctx)
        else:
            ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()

            if not self.screen_blank:
                ctx.font_size = 22
                ctx.text_align = ctx.CENTER
                ctx.rgb(0.96, 0.49, 0)
                if self.state == "poweroff":
                    ctx.move_to(0, -50).text("It is now safe to")
                    ctx.move_to(0, -28).text("unplug your badge.")
                    ctx.font_size = 16
                    ctx.rgb(1, 1, 1).move_to(0, -2).text(
                        "Press any key to blank screen."
                    )
                    ctx.move_to(0, 16).text("Press again to restore screen.")
                    ctx.move_to(0, 44).text("Battery does not")
                    ctx.move_to(0, 62).text("charge in this state.")
                    ctx.move_to(0, 80).text("Please use Standby.")
                else:
                    battery_line, current_line, state_line = (
                        self._get_standby_power_lines()
                    )

                    ctx.move_to(0, -40).text("Standby")
                    ctx.font_size = 16
                    ctx.rgb(1, 1, 1).move_to(0, -14).text(
                        "Press any key to blank screen."
                    )
                    ctx.move_to(0, 4).text("Press again to restore screen.")
                    ctx.move_to(0, 22).text("Press back to exit standby.")
                    ctx.move_to(0, 46).text(battery_line)
                    ctx.move_to(0, 64).text(current_line)
                    ctx.move_to(0, 82).text(state_line)
        ctx.restore()

        self.draw_overlays(ctx)

from __future__ import annotations

import sys

if sys.platform == "win32":

    class AgentHubLinuxDriver:
        """Placeholder so Windows can import app modules without Unix termios."""

else:
    import asyncio
    import errno
    import os
    import selectors
    import signal
    import termios
    import tty
    from codecs import getincrementaldecoder
    from concurrent.futures import Future, TimeoutError
    from threading import Thread, current_thread, main_thread

    from textual import events
    from textual._loop import loop_last
    from textual._parser import ParseError
    from textual._xterm_parser import XTermParser
    from textual.drivers._writer_thread import WriterThread
    from textual.drivers.linux_driver import LinuxDriver
    from textual.geometry import Size

    from cli.agent_cli.startup_debug import startup_log

    def _safe_terminal_utf8_decoder():
        return getincrementaldecoder("utf-8")(errors="replace").decode

    def _is_terminal_input_closed_error(exc: BaseException) -> bool:
        return isinstance(exc, OSError) and getattr(exc, "errno", None) in {
            errno.EBADF,
        }

    def _is_terminal_input_transient_error(exc: BaseException) -> bool:
        return isinstance(exc, OSError) and getattr(exc, "errno", None) == errno.EIO

    class AgentHubLinuxDriver(LinuxDriver):
        """Linux driver variant that avoids self-stopping on tty handoff checks."""

        def _recover_terminal_foreground(self) -> bool:
            if current_thread() is main_thread():
                return self._recover_terminal_foreground_now()
            loop = getattr(self, "_agenthub_event_loop", None)
            if loop is None or loop.is_closed():
                startup_log("driver.input_recover.no_event_loop")
                return False
            result: Future[bool] = Future()

            def _recover_on_event_loop() -> None:
                try:
                    result.set_result(self._recover_terminal_foreground_now())
                except Exception as exc:
                    startup_log(f"driver.input_recover.unexpected_error error={exc!r}")
                    result.set_result(False)

            try:
                loop.call_soon_threadsafe(_recover_on_event_loop)
                return bool(result.result(timeout=0.5))
            except TimeoutError:
                startup_log("driver.input_recover.timeout")
                return False
            except Exception as exc:
                startup_log(f"driver.input_recover.schedule_error error={exc!r}")
                return False

        def _recover_terminal_foreground_now(self) -> bool:
            if not os.isatty(self.fileno):
                return False
            try:
                foreground_pgrp = os.tcgetpgrp(self.fileno)
            except OSError as exc:
                startup_log(f"driver.input_recover.tcgetpgrp_error error={exc!r}")
                return False
            current_pgrp = os.getpgrp()
            if foreground_pgrp == current_pgrp:
                startup_log(
                    "driver.input_recover.already_foreground "
                    f"pgrp={current_pgrp} tpgid={foreground_pgrp}"
                )
                return True
            previous_ttou = signal.getsignal(signal.SIGTTOU)
            try:
                signal.signal(signal.SIGTTOU, signal.SIG_IGN)
                os.tcsetpgrp(self.fileno, current_pgrp)
            except OSError as exc:
                startup_log(
                    "driver.input_recover.tcsetpgrp_error "
                    f"pgrp={current_pgrp} foreground={foreground_pgrp} error={exc!r}"
                )
                return False
            finally:
                try:
                    signal.signal(signal.SIGTTOU, previous_ttou)
                except Exception:
                    pass
            try:
                recovered_tpgid = os.tcgetpgrp(self.fileno)
            except OSError:
                recovered_tpgid = current_pgrp
            startup_log(
                "driver.input_recover.tcsetpgrp_ok " f"pgrp={current_pgrp} tpgid={recovered_tpgid}"
            )
            return True

        def run_input_thread(self) -> None:
            """Wait for input and dispatch events without crashing on bad bytes."""
            selector = selectors.SelectSelector()
            selector.register(self.fileno, selectors.EVENT_READ)

            fileno = self.fileno
            event_read = selectors.EVENT_READ
            parser = XTermParser(self._debug)
            feed = parser.feed
            tick = parser.tick
            decode = _safe_terminal_utf8_decoder()
            read = os.read

            def process_selector_events(
                selector_events: list[tuple[selectors.SelectorKey, int]],
                final: bool = False,
            ) -> bool:
                for last, (_selector_key, mask) in loop_last(selector_events):
                    if mask & event_read:
                        try:
                            raw_data = read(fileno, 1024 * 4)
                        except OSError as exc:
                            if _is_terminal_input_closed_error(exc):
                                startup_log(
                                    "driver.input_thread.closed "
                                    f"errno={getattr(exc, 'errno', None)}"
                                )
                                return False
                            if _is_terminal_input_transient_error(exc):
                                startup_log(
                                    "driver.input_thread.transient_error "
                                    f"errno={getattr(exc, 'errno', None)}"
                                )
                                return self._recover_terminal_foreground()
                            raise
                        if not raw_data:
                            startup_log("driver.input_thread.empty_read")
                            return False
                        unicode_data = decode(raw_data, final=final and last)
                        if not unicode_data:
                            break
                        for event in feed(unicode_data):
                            self.process_message(event)
                for event in tick():
                    self.process_message(event)
                return True

            try:
                while not self.exit_event.is_set():
                    if not process_selector_events(selector.select(0.1)):
                        return
                try:
                    selector.unregister(self.fileno)
                except (KeyError, ValueError):
                    pass
                process_selector_events(selector.select(0.1), final=True)
            finally:
                selector.close()
                try:
                    for _event in feed(""):
                        pass
                except ParseError:
                    pass

        def start_application_mode(self) -> None:
            startup_log("driver.start_application_mode.begin")
            current_pgrp = os.getpgrp()
            try:
                startup_log(
                    "driver.tty_state.before "
                    f"pgrp={current_pgrp} "
                    f"tpgid={os.tcgetpgrp(self.fileno)}"
                )
            except Exception as exc:
                startup_log(f"driver.tty_state.before_error error={exc!r}")

            if os.isatty(self.fileno):
                try:
                    foreground_pgrp = os.tcgetpgrp(self.fileno)
                except OSError as exc:
                    foreground_pgrp = None
                    startup_log(f"driver.tcgetpgrp.error error={exc!r}")
                if foreground_pgrp is not None and foreground_pgrp != current_pgrp:
                    previous_ttou = signal.getsignal(signal.SIGTTOU)
                    try:
                        signal.signal(signal.SIGTTOU, signal.SIG_IGN)
                        os.tcsetpgrp(self.fileno, current_pgrp)
                        startup_log(
                            "driver.tcsetpgrp.ok "
                            f"pgrp={current_pgrp} "
                            f"tpgid={os.tcgetpgrp(self.fileno)}"
                        )
                    except OSError as exc:
                        startup_log(
                            "driver.tcsetpgrp.error "
                            f"pgrp={current_pgrp} "
                            f"foreground={foreground_pgrp} "
                            f"error={exc!r}"
                        )
                    finally:
                        try:
                            signal.signal(signal.SIGTTOU, previous_ttou)
                        except Exception:
                            pass
                previous_ttou = signal.getsignal(signal.SIGTTOU)
                previous_ttin = signal.getsignal(signal.SIGTTIN)
                try:
                    # Textual's default Linux driver converts SIGTTOU/SIGTTIN into
                    # SIGSTOP during a tcsetattr probe. In this environment that can
                    # falsely suspend the freshly-started foreground TUI. Ignore the
                    # stop signals for the probe instead of self-suspending.
                    signal.signal(signal.SIGTTOU, signal.SIG_IGN)
                    signal.signal(signal.SIGTTIN, signal.SIG_IGN)
                    termios.tcsetattr(
                        self.fileno,
                        termios.TCSANOW,
                        termios.tcgetattr(self.fileno),
                    )
                    startup_log("driver.tty_probe.ok")
                except termios.error as exc:
                    startup_log(f"driver.tty_probe.termios_error error={exc!r}")
                    return
                finally:
                    try:
                        signal.signal(signal.SIGTTOU, previous_ttou)
                        signal.signal(signal.SIGTTIN, previous_ttin)
                    except Exception:
                        pass
            try:
                startup_log(
                    "driver.tty_state.after_probe "
                    f"pgrp={os.getpgrp()} "
                    f"tpgid={os.tcgetpgrp(self.fileno)}"
                )
            except Exception as exc:
                startup_log(f"driver.tty_state.after_probe_error error={exc!r}")

            loop = asyncio.get_running_loop()
            self._agenthub_event_loop = loop

            def send_size_event() -> None:
                terminal_size = self._get_terminal_size()
                width, height = terminal_size
                textual_size = Size(width, height)
                event = events.Resize(textual_size, textual_size)
                asyncio.run_coroutine_threadsafe(
                    self._app._post_message(event),
                    loop=loop,
                )

            self._writer_thread = WriterThread(self._file)
            self._writer_thread.start()

            def on_terminal_resize(signum, stack) -> None:
                if not self._in_band_window_resize:
                    send_size_event()

            signal.signal(signal.SIGWINCH, on_terminal_resize)

            self.write("\x1b[?1049h")
            self._enable_mouse_support()
            try:
                self.attrs_before = termios.tcgetattr(self.fileno)
            except termios.error:
                self.attrs_before = None

            try:
                newattr = termios.tcgetattr(self.fileno)
            except termios.error as exc:
                startup_log(f"driver.termios.current_attr_error error={exc!r}")
            else:
                newattr[tty.LFLAG] = self._patch_lflag(newattr[tty.LFLAG])
                newattr[tty.IFLAG] = self._patch_iflag(newattr[tty.IFLAG])
                newattr[tty.CC][termios.VMIN] = 1
                try:
                    termios.tcsetattr(self.fileno, termios.TCSANOW, newattr)
                    startup_log("driver.termios.raw_mode.ok")
                except termios.error as exc:
                    startup_log(f"driver.termios.raw_mode_error error={exc!r}")

            self.write("\x1b[?25l")
            self.write("\x1b[?1004h")
            self.write("\x1b[>1u")

            self.flush()
            self._key_thread = Thread(target=self._run_input_thread)
            send_size_event()
            self._key_thread.start()
            self._request_terminal_sync_mode_support()
            self._query_in_band_window_resize()
            self._enable_bracketed_paste()
            self._disable_line_wrap()
            self._enable_mouse_support()

            if self._must_signal_resume:
                self._must_signal_resume = False
                asyncio.run_coroutine_threadsafe(
                    self._app._post_message(self.SignalResume()),
                    loop=loop,
                )
            startup_log("driver.start_application_mode.end")

# -*- coding: utf-8 -*-
"""CloakBrowser 的 Selenium 风格轻量适配层。"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from config import cloakbrowser as _cfg
from core.playwright_runtime import ensure_playwright_tempdir

logger = logging.getLogger(__name__)


@dataclass
class CloakOpenResult:
    profile_id: str = "cloakbrowser"
    raw: dict | None = None


class CloakElement:
    def __init__(self, page, locator=None, handle=None):
        self.page = page
        self.locator = locator
        self.handle = handle

    def _handle(self):
        if self.handle is not None:
            return self.handle
        return self.locator.element_handle(timeout=5000)

    def _eval(self, expression: str, arg: Any = None) -> Any:
        if self.locator is not None:
            try:
                return self.locator.evaluate(expression, arg, timeout=3000)
            except TypeError:
                old = 90000
                try:
                    self.page.set_default_timeout(3000)
                    return self.locator.evaluate(expression, arg)
                finally:
                    try:
                        self.page.set_default_timeout(old)
                    except Exception:
                        pass
        old = 90000
        try:
            self.page.set_default_timeout(3000)
            return self.handle.evaluate(expression, arg)
        finally:
            try:
                self.page.set_default_timeout(old)
            except Exception:
                pass

    def _eval_handle(self, expression: str, arg: Any = None) -> Any:
        h = self._handle()
        old = 90000
        try:
            self.page.set_default_timeout(3000)
            return h.evaluate_handle(expression, arg)
        finally:
            try:
                self.page.set_default_timeout(old)
            except Exception:
                pass

    def is_displayed(self) -> bool:
        try:
            if self.locator is not None:
                return bool(self.locator.is_visible(timeout=800))
            return bool(self.handle.evaluate("el => !!el && !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length) && getComputedStyle(el).visibility !== 'hidden' && getComputedStyle(el).display !== 'none'"))
        except Exception:
            return False

    def is_enabled(self) -> bool:
        try:
            if self.locator is not None:
                return bool(self.locator.is_enabled(timeout=800))
            return bool(self.handle.evaluate("el => !el.disabled && el.getAttribute('aria-disabled') !== 'true'"))
        except Exception:
            return False

    def click(self) -> None:
        try:
            if self.locator is not None:
                self.locator.click(timeout=3000, force=True)
            else:
                self.handle.click(timeout=3000, force=True)
        except Exception:
            try:
                if self.locator is not None:
                    self.locator.evaluate("el => el.click()")
                elif self.handle is not None:
                    self.handle.evaluate("el => el.click()")
            except Exception:
                pass

    def _set_input_value(self, value: str) -> None:
        script = """(el, value) => {
          if (!el) return false;
          const tag = String(el.tagName || '').toLowerCase();
          try { el.focus(); } catch (e) {}
          const proto = tag === 'textarea' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
          const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
          if (setter) setter.call(el, value);
          else el.value = value;
          el.dispatchEvent(new Event('input', {bubbles:true}));
          el.dispatchEvent(new Event('change', {bubbles:true}));
          return String(el.value || '');
        }"""
        if self.locator is not None:
            try:
                self.locator.evaluate(script, value, timeout=3000)
            except TypeError:
                old = 90000
                try:
                    self.page.set_default_timeout(3000)
                    self.locator.evaluate(script, value)
                finally:
                    try:
                        self.page.set_default_timeout(old)
                    except Exception:
                        pass
        elif self.handle is not None:
            old = 90000
            try:
                self.page.set_default_timeout(3000)
                self.handle.evaluate(script, value)
            finally:
                try:
                    self.page.set_default_timeout(old)
                except Exception:
                    pass
        else:
            raise RuntimeError("CloakElement has no locator/handle")

    def clear(self) -> None:
        try:
            self._set_input_value("")
        except Exception:
            try:
                self.page.keyboard.press("Control+A")
            except Exception:
                self.page.keyboard.press("Meta+A")
            self.page.keyboard.press("Backspace")

    @property
    def tag_name(self) -> str:
        try:
            return str(self._eval("el => el.tagName.toLowerCase()") or "")
        except Exception:
            return ""

    @property
    def text(self) -> str:
        try:
            return str(self._eval("el => (el.innerText || el.textContent || '').trim()") or "")
        except Exception:
            return ""

    def send_keys(self, *values: str) -> None:
        # 兼容 Selenium 逐字输入。不要 click：人工化路径会按 1～2 个字符调用，
        # 每次 click 都会把光标点进输入框中间，邮箱被插成乱码。
        # 也不要用 locator.fill()：同样会把整框覆盖成当前这一小段。
        special = {
            "\ue003": "Backspace",
            "\ue017": "Delete",
            "\ue006": "Enter",
            "\ue007": "Enter",
            "\ue004": "Tab",
            "\ue00c": "Escape",
        }
        for raw in values:
            text = str(raw or "")
            if not text:
                continue
            if "\ue03d" in text or "\ue009" in text:
                try:
                    self.page.keyboard.press("Control+A")
                except Exception:
                    self.page.keyboard.press("Meta+A")
                leftover = text.replace("\ue03d", "").replace("\ue009", "")
                if leftover.lower() == "a" or leftover == "":
                    continue
                text = leftover
            if text in special:
                self.page.keyboard.press(special[text])
                continue
            # 不要 locator.fill()：无头 ChatGPT 登录页上会卡死可操作性等待。
            if len(text) >= 3:
                try:
                    self._set_input_value(text)
                    continue
                except Exception:
                    pass
            try:
                self.page.keyboard.insert_text(text)
            except Exception:
                self.page.keyboard.type(text, delay=10)

    def get_attribute(self, name: str) -> str | None:
        try:
            if self.locator is not None:
                return self.locator.get_attribute(name, timeout=1000)
            return self.handle.get_attribute(name)
        except Exception:
            return None


class _SwitchTo:
    def __init__(self, driver: "CloakSeleniumDriver"):
        self._driver = driver

    def window(self, handle: str) -> None:
        self._driver._switch_window(handle)


class CloakSeleniumDriver:
    """只实现本项目 Roxy Selenium 流程实际用到的 WebDriver 子集。"""

    def __init__(self, browser: Any, context: Any | None, page: Any, proxy_relay: Any | None = None):
        self.browser = browser
        self.context = context
        self.page = page
        self._proxy_relay = proxy_relay
        self._page_load_timeout_ms = int(getattr(_cfg, "CLOAK_SELENIUM_TIMEOUT", 90) or 90) * 1000
        self.switch_to = _SwitchTo(self)

    @property
    def current_url(self) -> str:
        return str(getattr(self.page, "url", "") or "")

    @property
    def window_handles(self) -> list[str]:
        pages = self._pages()
        return [str(i) for i in range(len(pages))]

    def _pages(self) -> list[Any]:
        try:
            if self.context is not None:
                return list(self.context.pages)
        except Exception:
            pass
        try:
            contexts = list(getattr(self.browser, "contexts", []) or [])
            pages = []
            for ctx in contexts:
                pages.extend(list(getattr(ctx, "pages", []) or []))
            return pages or [self.page]
        except Exception:
            return [self.page]

    def _switch_window(self, handle: str) -> None:
        pages = self._pages()
        idx = int(handle)
        self.page = pages[idx]
        try:
            self.page.bring_to_front()
        except Exception:
            pass

    def set_page_load_timeout(self, seconds: int) -> None:
        self._page_load_timeout_ms = int(seconds) * 1000
        try:
            self.page.set_default_navigation_timeout(self._page_load_timeout_ms)
            self.page.set_default_timeout(self._page_load_timeout_ms)
        except Exception:
            pass

    def get(self, url: str) -> None:
        self.page.goto(url, wait_until="domcontentloaded", timeout=self._page_load_timeout_ms)

    def back(self) -> None:
        self.page.go_back(wait_until="domcontentloaded", timeout=self._page_load_timeout_ms)

    def refresh(self) -> None:
        self.page.reload(wait_until="domcontentloaded", timeout=self._page_load_timeout_ms)

    def quit(self) -> None:
        try:
            if self.context is not None:
                self.context.close()
        except Exception:
            pass
        try:
            self.browser.close()
        except Exception:
            pass
        relay, self._proxy_relay = self._proxy_relay, None
        if relay is not None:
            relay.close()

    def find_elements(self, by: Any, selector: str) -> list[CloakElement]:
        loc = self._locator(by, selector)
        try:
            count = min(int(loc.count()), 200)
        except Exception:
            count = 0
        return [CloakElement(self.page, loc.nth(i)) for i in range(count)]

    def find_element(self, by: Any, selector: str) -> CloakElement:
        els = self.find_elements(by, selector)
        if not els:
            raise RuntimeError(f"找不到页面元素: {selector}")
        return els[0]

    def _locator(self, by: Any, selector: str):
        by_s = str(by or "").lower()
        if "xpath" in by_s or str(selector).startswith("//"):
            return self.page.locator(f"xpath={selector}")
        return self.page.locator(selector)

    def execute_script(self, script: str, *args: Any) -> Any:
        return self._evaluate(script, args=args, async_mode=False)

    def execute_async_script(self, script: str, *args: Any) -> Any:
        return self._evaluate(script, args=args, async_mode=True)

    def execute_cdp_cmd(self, cmd: str, params: dict | None = None) -> Any:
        params = params or {}
        try:
            client = self.context.new_cdp_session(self.page) if self.context is not None else self.page.context.new_cdp_session(self.page)
            return client.send(cmd, params)
        except Exception as exc:
            logger.debug("[Cloak] CDP 命令失败 %s: %s", cmd, exc)
            return None

    def _serialize_args(self, args: tuple[Any, ...]) -> tuple[CloakElement | None, list[Any]]:
        """拆分 Selenium 脚本参数。

        Playwright 的 JSHandle/ElementHandle 不能可靠地嵌在 dict/list payload 中跨
        page.evaluate 传递；Selenium 脚本最常见模式是 `arguments[0]` 为元素，
        因此这里把第一个 CloakElement 作为真实 DOM `el` 传入，其它参数保持
        JSON 可序列化。
        """
        first_el = args[0] if args and isinstance(args[0], CloakElement) else None
        rest = list(args[1:] if first_el else args)
        cleaned = []
        for item in rest:
            if isinstance(item, CloakElement):
                # 极少数脚本会传多个元素；用真实 handle 直接会在嵌套 payload 中失效，
                # 这里退化为 None，比把错误对象传进 JS 更安全。
                cleaned.append(None)
            else:
                cleaned.append(item)
        return first_el, cleaned

    @staticmethod
    def _unwrap_js_result(page, handle: Any) -> Any:
        try:
            element = handle.as_element()
        except Exception:
            element = None
        if element is not None:
            return CloakElement(page, handle=element)
        try:
            return handle.json_value()
        except Exception as exc:
            msg = str(exc)
            if "Execution context was destroyed" in msg or "navigation" in msg.lower():
                logger.info("[Cloak] JS 执行后页面发生跳转，忽略返回值读取失败：%s", msg[:160])
                return {"ok": True, "reason": "navigation_after_script"}
            raise
        finally:
            try:
                handle.dispose()
            except Exception:
                pass

    def _evaluate(self, script: str, args: tuple[Any, ...], async_mode: bool) -> Any:
        first_el, serial_args = self._serialize_args(args)
        if async_mode:
            wrapper = """async ({script, args}) => {
              return await new Promise((resolve) => {
                const fn = new Function(...args.map((_, i) => 'a' + i), '__cloak_done', script);
                const timer = setTimeout(() => resolve({__cloak_timeout:true}), 120000);
                const __cloak_done = (v) => { clearTimeout(timer); resolve(v); };
                try { fn(...args, __cloak_done); } catch (e) { clearTimeout(timer); resolve({ok:false, error:String(e)}); }
              });
            }"""
            element_wrapper = """async (el, payload) => {
              const args = [el, ...payload.args];
              return await new Promise((resolve) => {
                const fn = new Function(...args.map((_, i) => 'a' + i), '__cloak_done', payload.script);
                const timer = setTimeout(() => resolve({__cloak_timeout:true}), 120000);
                const __cloak_done = (v) => { clearTimeout(timer); resolve(v); };
                try { fn(...args, __cloak_done); } catch (e) { clearTimeout(timer); resolve({ok:false, error:String(e)}); }
              });
            }"""
            if first_el is not None:
                result = first_el._eval(element_wrapper, {"script": script, "args": serial_args})
            else:
                result = self.page.evaluate(wrapper, {"script": script, "args": serial_args})
            if isinstance(result, dict) and result.get("__cloak_timeout"):
                raise TimeoutError("execute_async_script timeout")
            return result

        # Selenium 脚本把第一个参数当 DOM 节点，并用 arguments[0]。
        # Playwright locator.evaluate 的第一个形参才是元素；payload 必须是第二个。
        # JSON 结果走 evaluate（可超时）；真正返回 DOM 节点时再 evaluate_handle。
        payload = {"script": script, "args": serial_args}
        inspect_wrapper = """(extra) => {
          const fn = new Function(extra.script);
          const result = fn.apply(null, extra.args || []);
          if (result && result.nodeType === 1) return {kind:'el'};
          if (result && typeof result === 'object') {
            const elKeys = Object.keys(result).filter(k => result[k] && result[k].nodeType === 1);
            if (elKeys.length) return {kind:'mixed', elKeys};
          }
          return {kind:'json', value: result};
        }"""
        inspect_element_wrapper = """(element, extra) => {
          const args = [element, ...(extra && extra.args ? extra.args : [])];
          const fn = new Function(extra.script);
          const result = fn.apply(null, args);
          if (result && result.nodeType === 1) return {kind:'el'};
          if (result && typeof result === 'object') {
            const elKeys = Object.keys(result).filter(k => result[k] && result[k].nodeType === 1);
            if (elKeys.length) return {kind:'mixed', elKeys};
          }
          return {kind:'json', value: result};
        }"""
        element_wrapper = """(element, extra) => {
          const args = [element, ...(extra && extra.args ? extra.args : [])];
          const fn = new Function(extra.script);
          return fn.apply(null, args);
        }"""
        wrapper = """(extra) => {
          const fn = new Function(extra.script);
          return fn.apply(null, extra.args || []);
        }"""
        if first_el is not None:
            try:
                inspected = first_el._eval(inspect_element_wrapper, payload)
            except Exception as exc:
                msg = str(exc)
                if "Execution context was destroyed" in msg or "navigation" in msg.lower() or "Timeout" in msg:
                    logger.info("[Cloak] 元素脚本 inspect 跳转/超时：%s", msg[:160])
                    return {"ok": True, "reason": "navigation_or_timeout"}
                raise
            return self._materialize_inspected(inspected, payload, first_el=first_el, element_wrapper=element_wrapper, wrapper=wrapper)
        inspected = self._eval_json(inspect_wrapper, payload)
        return self._materialize_inspected(inspected, payload, first_el=None, element_wrapper=element_wrapper, wrapper=wrapper)

    def _materialize_inspected(self, inspected: Any, payload: dict, *, first_el: Any, element_wrapper: str, wrapper: str) -> Any:
        if isinstance(inspected, dict) and inspected.get("kind") == "json":
            return inspected.get("value")
        if isinstance(inspected, dict) and inspected.get("kind") == "el":
            if first_el is not None:
                handle = first_el._eval_handle(element_wrapper, payload)
            else:
                handle = self._eval_handle_with_timeout(wrapper, payload)
            return self._unwrap_js_result(self.page, handle)
        if isinstance(inspected, dict) and inspected.get("kind") == "mixed":
            return self._materialize_mixed(payload, inspected.get("elKeys") or [], first_el=first_el, element_wrapper=element_wrapper)
        return inspected

    def _materialize_mixed(self, payload: dict, el_keys: list[Any], *, first_el: Any, element_wrapper: str) -> dict:
        json_extract = """(extra) => {
          const fn = new Function(extra.script);
          const result = fn.apply(null, extra.args || []);
          const out = {};
          for (const k of Object.keys(result || {})) {
            if (!(result[k] && result[k].nodeType === 1)) out[k] = result[k];
          }
          return out;
        }"""
        el_extract = """(extra) => {
          const fn = new Function(extra.script);
          const result = fn.apply(null, extra.args || []);
          return result ? result[extra.key] : null;
        }"""
        el_extract_from_element = """(element, extra) => {
          const args = [element, ...(extra && extra.args ? extra.args : [])];
          const fn = new Function(extra.script);
          const result = fn.apply(null, args);
          return result ? result[extra.key] : null;
        }"""
        json_extract_from_element = """(element, extra) => {
          const args = [element, ...(extra && extra.args ? extra.args : [])];
          const fn = new Function(extra.script);
          const result = fn.apply(null, args);
          const out = {};
          for (const k of Object.keys(result || {})) {
            if (!(result[k] && result[k].nodeType === 1)) out[k] = result[k];
          }
          return out;
        }"""
        if first_el is not None:
            out = first_el._eval(json_extract_from_element, payload) or {}
        else:
            out = self._eval_json(json_extract, payload) or {}
        if not isinstance(out, dict):
            out = {"ok": True, "value": out}
        for key in el_keys:
            extra = dict(payload)
            extra["key"] = key
            try:
                if first_el is not None:
                    handle = first_el._eval_handle(el_extract_from_element, extra)
                else:
                    handle = self._eval_handle_with_timeout(el_extract, extra)
                out[key] = self._unwrap_js_result(self.page, handle)
            except Exception as exc:
                logger.info("[Cloak] mixed 元素提取失败 key=%s err=%s", key, str(exc)[:160])
                out[key] = None
        return out

    def _eval_json(self, expression: str, arg: Any) -> Any:
        try:
            return self.page.evaluate(expression, arg, timeout=5000)
        except TypeError:
            old = getattr(self, "_page_load_timeout_ms", 90000)
            try:
                self.page.set_default_timeout(5000)
                return self.page.evaluate(expression, arg)
            finally:
                try:
                    self.page.set_default_timeout(old)
                except Exception:
                    pass
        except Exception as exc:
            msg = str(exc)
            if "Execution context was destroyed" in msg or "navigation" in msg.lower() or "Timeout" in msg:
                logger.info("[Cloak] JS evaluate 在跳转/超时后放弃：%s", msg[:160])
                return {"ok": True, "reason": "navigation_or_timeout"}
            raise

    def _eval_handle_with_timeout(self, expression: str, arg: Any) -> Any:
        old = getattr(self, "_page_load_timeout_ms", 90000)
        try:
            self.page.set_default_timeout(5000)
        except Exception:
            pass
        try:
            return self.page.evaluate_handle(expression, arg)
        except Exception as exc:
            msg = str(exc)
            if "Execution context was destroyed" in msg or "navigation" in msg.lower() or "Timeout" in msg:
                logger.info("[Cloak] JS evaluate_handle 在跳转/超时后放弃：%s", msg[:160])
                return type("EmptyHandle", (), {"as_element": lambda self: None, "json_value": lambda self: {"ok": True, "reason": "navigation_or_timeout"}, "dispose": lambda self: None})()
            raise
        finally:
            try:
                self.page.set_default_timeout(old)
            except Exception:
                pass


def _normalize_proxy(proxy: str | None) -> str | None:
    proxy = str(proxy or "").strip()
    if not proxy:
        return None
    return proxy.replace("socks5h://", "socks5://")


def _detect_cloak_exit_geo(proxy_url: str | None = None) -> dict:
    """按当前/代理出口检测地理信息，供 Cloak 显式 locale/timezone 使用。"""
    try:
        import requests
        from config import browser as _browser_cfg
        endpoints = list(getattr(_browser_cfg, "IP_GEO_ENDPOINTS", []) or [])
        timeout = float(getattr(_browser_cfg, "IP_GEO_TIMEOUT", 6) or 6)
    except Exception:
        return {}
    proxies = None
    if proxy_url:
        proxies = {"http": proxy_url, "https": proxy_url}
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    for url in endpoints:
        try:
            resp = requests.get(url, headers=headers, proxies=proxies, timeout=timeout)
            if resp.status_code != 200:
                continue
            data = resp.json()
            timezone = data.get("timezone")
            if isinstance(timezone, dict):
                timezone = timezone.get("id") or timezone.get("name")
            geo = {
                "ip": data.get("ip") or data.get("query"),
                "country": (data.get("country") or data.get("country_code") or data.get("countryCode") or "").upper(),
                "region": data.get("region") or data.get("regionName"),
                "city": data.get("city"),
                "timezone": timezone or "",
                "org": data.get("org") or data.get("isp") or (data.get("connection") or {}).get("org"),
            }
            if geo.get("country") or geo.get("timezone"):
                logger.info(
                    "[Cloak] 出口IP地理信息：ip=%s country=%s city=%s timezone=%s",
                    geo.get("ip") or "?", geo.get("country") or "?", geo.get("city") or "?", geo.get("timezone") or "?",
                )
                return geo
        except Exception as exc:
            logger.debug("[Cloak] 出口 IP 地理检测失败 endpoint=%s: %s: %s", url, type(exc).__name__, exc)
    return {}


def _build_cloak_locale_options(proxy_url: str | None = None) -> dict:
    """生成 Cloak/Playwright 双层语言时区配置。"""
    explicit_locale = str(getattr(_cfg, "CLOAK_LOCALE", "") or "").strip()
    explicit_timezone = str(getattr(_cfg, "CLOAK_TIMEZONE", "") or "").strip()
    out = {}
    if explicit_locale:
        out["locale"] = explicit_locale
        # Accept-Language 用 config.browser 自动推断更完整；显式时给一个保守值。
        out["accept_language"] = f"{explicit_locale},{explicit_locale.split('-')[0]};q=0.9,en-US;q=0.8,en;q=0.7"
    if explicit_timezone:
        out["timezone"] = explicit_timezone
    if explicit_locale and explicit_timezone:
        return out
    if not bool(getattr(_cfg, "CLOAK_GEOIP", True)):
        return out
    try:
        from config.browser import build_browser_environment
        geo = _detect_cloak_exit_geo(proxy_url)
        profile = build_browser_environment(geo)
        out.setdefault("locale", str(profile.get("navigator_language") or ""))
        out.setdefault("timezone", str(profile.get("timezone_iana") or ""))
        out.setdefault("accept_language", str(profile.get("accept_language") or ""))
        out["geo"] = geo
    except Exception as exc:
        logger.debug("[Cloak] 构建自动语言/时区失败：%s: %s", type(exc).__name__, exc)
    return {k: v for k, v in out.items() if v}


def build_cloak_driver(proxy: str | None = None) -> tuple[CloakSeleniumDriver, CloakOpenResult]:
    """启动 CloakBrowser 并返回 Selenium 风格 driver。

    proxy=None  时按 config.proxy.PROXY_POOL 随机抽取；
    proxy=""    时显式禁用代理；
    proxy="..." 时使用指定代理。
    """
    proxy_relay = None
    proxy_pool_target = ""
    if proxy is None and bool(getattr(_cfg, "CLOAK_USE_PROXY", True)):
        try:
            from config.proxy import pick_proxy
        except Exception:
            proxy = None
        else:
            from core.proxy_chain import open_proxy_pool_proxy
            proxy_pool_target = str(pick_proxy() or "").strip()
            proxy, proxy_relay = open_proxy_pool_proxy(proxy_pool_target)
    try:
        from cloakbrowser import launch, launch_persistent_context
    except ImportError as exc:
        raise RuntimeError("未安装 cloakbrowser，请执行：pip install cloakbrowser") from exc
    tmp_dir = ensure_playwright_tempdir()
    logger.info("[Cloak] Playwright 临时目录：%s", tmp_dir)

    launch_args = list(getattr(_cfg, "CLOAK_EXTRA_ARGS", []) or [])
    seed = str(getattr(_cfg, "CLOAK_FINGERPRINT_SEED", "") or "").strip()
    if seed:
        launch_args.append(f"--fingerprint={seed}")

    proxy_url = _normalize_proxy(proxy) if bool(getattr(_cfg, "CLOAK_USE_PROXY", True)) else None
    locale_opts = _build_cloak_locale_options(proxy_url)
    # geoip=True 交给 CloakBrowser 根据当前出口 IP 自动匹配 timezone/locale/WebRTC。
    # 之前只有显式 proxy_url 时才开启；如果用户走系统代理/VPN/透明代理，代码层面
    # 看不到 proxy_url，会误关 geoip，导致语言/时区不跟随出口。这里改为完全尊重配置。
    opts = {
        "headless": bool(getattr(_cfg, "CLOAK_HEADLESS", False)),
        "humanize": bool(getattr(_cfg, "CLOAK_HUMANIZE", True)),
        "geoip": bool(getattr(_cfg, "CLOAK_GEOIP", True)),
    }
    if locale_opts.get("locale"):
        opts["locale"] = locale_opts["locale"]
    if locale_opts.get("timezone"):
        opts["timezone"] = locale_opts["timezone"]
    if proxy_url:
        opts["proxy"] = proxy_url
    if launch_args:
        opts["args"] = launch_args
    license_key = str(getattr(_cfg, "CLOAK_LICENSE_KEY", "") or "").strip()
    if license_key:
        opts["license_key"] = license_key

    user_data_dir = str(getattr(_cfg, "CLOAK_USER_DATA_DIR", "") or "").strip()
    logger.info(
        "[Cloak] 启动 CloakBrowser：headless=%s humanize=%s geoip=%s proxy=%s locale=%s timezone=%s accept_language=%s persistent=%s",
        opts.get("headless"), opts.get("humanize"), opts.get("geoip"),
        proxy_url or "无", opts.get("locale") or "自动/默认", opts.get("timezone") or "自动/默认",
        locale_opts.get("accept_language") or "自动/默认", bool(user_data_dir),
    )
    context_kwargs = {}
    if locale_opts.get("locale"):
        context_kwargs["locale"] = locale_opts["locale"]
    if locale_opts.get("timezone"):
        context_kwargs["timezone_id"] = locale_opts["timezone"]
    if locale_opts.get("accept_language"):
        context_kwargs["extra_http_headers"] = {"Accept-Language": locale_opts["accept_language"]}

    if user_data_dir:
        context = launch_persistent_context(user_data_dir, **opts)
        page = context.new_page()
        browser = getattr(context, "browser", None) or context
        # persistent context 的 locale/timezone 已通过 launch_persistent_context 参数传入。
    else:
        browser = launch(**opts)
        context = browser.new_context(**context_kwargs)
        page = context.new_page()

    driver = CloakSeleniumDriver(browser=browser, context=context, page=page, proxy_relay=proxy_relay)
    # Roxy/Cloak 共用部分页面操作函数；给共享函数一个显式日志前缀，
    # 避免 Cloak 注册流程里出现 `[Roxy注册]`。
    driver._registration_log_prefix = "[Cloak注册]"
    driver.set_page_load_timeout(int(getattr(_cfg, "CLOAK_SELENIUM_TIMEOUT", 90) or 90))
    return driver, CloakOpenResult(raw={
        "driver": "cloakbrowser",
        "proxy": proxy_url,
        "proxy_pool_target": proxy_pool_target or proxy_url,
        "locale": locale_opts,
        "options": {k: v for k, v in opts.items() if k != "license_key"},
    })

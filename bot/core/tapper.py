
import asyncio
from time import time
from random import randint
from urllib.parse import unquote
from .headers import headers
import math

import aiohttp
from aiohttp_proxy import ProxyConnector
from better_proxy import Proxy
from pyrogram import Client
from pyrogram.errors import Unauthorized, UserDeactivated, AuthKeyUnregistered, FloodWait
from pyrogram.raw.functions.messages import RequestWebView

from bot.config import settings
from bot.utils import logger
from bot.utils.scripts import escape_html
from bot.exceptions import InvalidSession


class Tapper:
    def __init__(self, tg_client: Client):
        self.session_name = tg_client.name
        self.tg_client = tg_client

    async def get_tg_web_data(self, proxy: str | None) -> str:
        if proxy:
            proxy = Proxy.from_str(proxy)
            proxy_dict = dict(
                scheme=proxy.protocol,
                hostname=proxy.host,
                port=proxy.port,
                username=proxy.login,
                password=proxy.password
            )
        else:
            proxy_dict = None

        self.tg_client.proxy = proxy_dict

        try:
            if not self.tg_client.is_connected:
                try:
                    await self.tg_client.connect()
                except (Unauthorized, UserDeactivated, AuthKeyUnregistered):
                    raise InvalidSession(self.session_name)

            dialogs = self.tg_client.get_dialogs()
            async for dialog in dialogs:
                if dialog.chat and dialog.chat.username and dialog.chat.username == 'Gleam_AquaProtocol_Bot':
                    break

            while True:
                try:
                    peer = await self.tg_client.resolve_peer('Gleam_AquaProtocol_Bot')
                    break
                except FloodWait as fl:
                    fls = fl.value

                    logger.warning(f"{self.session_name} | FloodWait {fl}")
                    fls *= 2
                    logger.info(f"{self.session_name} | Sleep {fls}s")

                    await asyncio.sleep(fls)

            web_view = await self.tg_client.invoke(RequestWebView(
                peer=peer,
                bot=peer,
                platform='android',
                from_bot_menu=False,
                url='https://api.gleam.bot/'
            ))

            auth_url = web_view.url
            tg_web_data = unquote(
                string=unquote(
                    string=auth_url.split('tgWebAppData=', maxsplit=1)[1].split('&tgWebAppVersion', maxsplit=1)[0]))

            if self.tg_client.is_connected:
                await self.tg_client.disconnect()

            return tg_web_data

        except InvalidSession as error:
            raise error

        except Exception as error:
            logger.error(
                f"{self.session_name} | Unknown error during Authorization: {error}")
            await asyncio.sleep(delay=3)

    async def login(self, http_client: aiohttp.ClientSession, tg_web_data: str) -> str:
        response_text = ''
        try:
            response = await http_client.post(url='https://api.gleam.bot/auth',
                                              json={"initData": tg_web_data, "project": "Aqua Protocol"})
            response_text = await response.text()
            response.raise_for_status()

            response_json = await response.json()
            return response_json
        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error while getting Login Data: {error} | "
                         f"Response text: {escape_html(response_text)[:256]}...")
            await asyncio.sleep(delay=3)

    async def claimFarm(self, http_client: aiohttp.ClientSession, tg_web_data: str) -> str:
        response_text = ''
        try:
            response = await http_client.post(url='https://api.gleam.bot/claim',
                                              json={"initData": tg_web_data, "project": "Aqua Protocol"})
            response_text = await response.text()
            response.raise_for_status()

            response_json = await response.json()
            return response_json
        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error while calming farm: {error} | "
                         f"Response text: {escape_html(response_text)[:256]}...")
            await asyncio.sleep(delay=30)

    async def startFarm(self, http_client: aiohttp.ClientSession, tg_web_data: str) -> str:
        response_text = ''
        try:
            response = await http_client.post(url='https://api.gleam.bot/start-farming',
                                              json={"initData": tg_web_data, "project": "Aqua Protocol"})
            response_text = await response.text()
            response.raise_for_status()

            response_json = await response.json()
            return response_json
        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error while starting farm: {error} | "
                         f"Response text: {escape_html(response_text)[:256]}...")
            await asyncio.sleep(delay=3)

    async def check_proxy(self, http_client: aiohttp.ClientSession, proxy: Proxy) -> None:
        try:
            response = await http_client.get(url='https://httpbin.org/ip', timeout=aiohttp.ClientTimeout(5))
            ip = (await response.json()).get('origin')
            logger.info(f"{self.session_name} | Proxy IP: {ip}")
        except Exception as error:
            logger.error(
                f"{self.session_name} | Proxy: {proxy} | Error: {error}")

    async def run(self, proxy: str | None) -> None:

        proxy_conn = ProxyConnector().from_url(proxy) if proxy else None
        http_client = aiohttp.ClientSession(
            headers=headers, connector=proxy_conn)

        if proxy:
            await self.check_proxy(http_client=http_client, proxy=proxy)

        tg_web_data = await self.get_tg_web_data(proxy=proxy)
        while True:
            try:
                if http_client.closed:
                    if proxy_conn:
                        if not proxy_conn.closed:
                            proxy_conn.close()

                    proxy_conn = ProxyConnector().from_url(proxy) if proxy else None
                    http_client = aiohttp.ClientSession(
                        headers=headers, connector=proxy_conn)

                login_data = await self.login(http_client=http_client, tg_web_data=tg_web_data)

                farm_finish_time = math.ceil(int(
                    login_data['farm_started_at'])/1000) + settings.FARM_TIME_IN_SECONDS
                await asyncio.sleep(delay=5)
                if farm_finish_time < (int(time())):
                    sleep_between = randint(a=50, b=100)
                    logger.info(f"Calming Farm balance")
                    await self.claimFarm(http_client=http_client, tg_web_data=tg_web_data)
                    sleep_between = randint(a=10, b=20)
                    await asyncio.sleep(delay=sleep_between)
                    logger.info(f"Start Farm")
                    await self.startFarm(http_client=http_client, tg_web_data=tg_web_data)
                    continue



                await http_client.close()
                if proxy_conn:
                    if not proxy_conn.closed:
                        proxy_conn.close()
                farm_finish_in_seconds = (farm_finish_time - (int(time())))
                logger.info(f"Sleep Time {farm_finish_in_seconds}s")
                await asyncio.sleep(delay=farm_finish_in_seconds)
            except InvalidSession as error:
                raise error

            except Exception as error:
                logger.error(f"{self.session_name} | Unknown error: {error}")
                await asyncio.sleep(delay=10)


async def run_tapper(tg_client: Client, proxy: str | None):
    try:
        await Tapper(tg_client=tg_client).run(proxy=proxy)
    except InvalidSession:
        logger.error(f"{tg_client.name} | Invalid Session")

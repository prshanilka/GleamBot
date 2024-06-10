import asyncio
from time import time
from random import randint
from urllib.parse import unquote
import math

import aiohttp
from aiohttp_proxy import ProxyConnector
from better_proxy import Proxy
from pyrogram import Client
from pyrogram.errors import Unauthorized, UserDeactivated, AuthKeyUnregistered, FloodWait
from pyrogram.raw.functions.messages import RequestWebView


from .headers import headers
from bot.config import settings
from bot.utils import logger
from bot.utils.scripts import escape_html
from bot.exceptions import InvalidSession


class Tapper:
    def __init__(self, tg_client: Client):
        self.session_name = tg_client.name
        self.tg_client = tg_client

    async def get_tg_web_data(self, proxy: str | None) -> str:
        proxy_dict = None
        if proxy:
            proxy = Proxy.from_str(proxy)
            proxy_dict = {
                'scheme': proxy.protocol,
                'hostname': proxy.host,
                'port': proxy.port,
                'username': proxy.login,
                'password': proxy.password
            }

        self.tg_client.proxy = proxy_dict

        if not self.tg_client.is_connected:
            try:
                await self.tg_client.connect()
            except (Unauthorized, UserDeactivated, AuthKeyUnregistered):
                raise InvalidSession(self.session_name)

        try:
            peer = None
            async for dialog in self.tg_client.get_dialogs():
                if dialog.chat and dialog.chat.username == 'Gleam_AquaProtocol_Bot':
                    peer = await self.tg_client.resolve_peer(dialog.chat.id)
                    break

            if not peer:
                peer = await self.tg_client.resolve_peer('Gleam_AquaProtocol_Bot')

            web_view = await self.tg_client.invoke(RequestWebView(
                peer=peer,
                bot=peer,
                platform='android',
                from_bot_menu=False,
                url='https://api.gleam.bot/'
            ))

            auth_url = web_view.url
            tg_web_data = unquote(auth_url.split('tgWebAppData=', 1)[1].split('&tgWebAppVersion', 1)[0])

            if self.tg_client.is_connected:
                await self.tg_client.disconnect()

            return tg_web_data

        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error during Authorization: {error}")
            await asyncio.sleep(3)
            raise

    async def login(self, http_client: aiohttp.ClientSession, tg_web_data: str) -> dict:
        response_text = ''
        try:
            response = await http_client.post(
                url='https://api.gleam.bot/auth',
                json={"initData": tg_web_data, "project": "Aqua Protocol"}
            )
            response_text = await response.text()
            response.raise_for_status()
            return await response.json()

        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error while getting Login Data: {error} | "
                         f"Response text: {escape_html(response_text)[:256]}...")
            await asyncio.sleep(3)
            raise

    async def claim_farm(self, http_client: aiohttp.ClientSession, tg_web_data: str) -> dict:
        response_text = ''
        try:
            response = await http_client.post(
                url='https://api.gleam.bot/claim',
                json={"initData": tg_web_data, "project": "Aqua Protocol"}
            )
            response_text = await response.text()
            response.raise_for_status()
            return await response.json()

        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error while claiming farm: {error} | "
                         f"Response text: {escape_html(response_text)[:256]}...")
            await asyncio.sleep(30)
            raise

    async def start_farm(self, http_client: aiohttp.ClientSession, tg_web_data: str) -> dict:
        response_text = ''
        try:
            response = await http_client.post(
                url='https://api.gleam.bot/start-farming',
                json={"startedAt":int(time())*1000,"initData": tg_web_data, "project": "Aqua Protocol"}
            )
            response_text = await response.text()
            response.raise_for_status()
            return await response.json()

        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error while starting farm: {error} | "
                         f"Response text: {escape_html(response_text)[:256]}...")
            await asyncio.sleep(3)
            raise

    async def check_proxy(self, http_client: aiohttp.ClientSession, proxy: Proxy) -> None:
        try:
            response = await http_client.get(url='https://httpbin.org/ip', timeout=aiohttp.ClientTimeout(5))
            ip = (await response.json()).get('origin')
            logger.info(f"{self.session_name} | Proxy IP: {ip}")
        except Exception as error:
            logger.error(f"{self.session_name} | Proxy: {proxy} | Error: {error}")

    async def run(self, proxy: str | None) -> None:
        proxy_conn = ProxyConnector().from_url(proxy) if proxy else None

        async with aiohttp.ClientSession(headers=headers, connector=proxy_conn) as http_client:
            if proxy:
                await self.check_proxy(http_client=http_client, proxy=Proxy.from_str(proxy))

            tg_web_data = await self.get_tg_web_data(proxy=proxy)
            while True:
                try:
                    login_data = await self.login(http_client=http_client, tg_web_data=tg_web_data)
                    farm_started_at = login_data.get('farm_started_at')

                    if farm_started_at is None:
                        await self.start_farm(http_client=http_client, tg_web_data=tg_web_data)
                        continue

                    farm_finish_time = math.ceil(int(farm_started_at) / 1000) + settings.FARM_TIME_IN_SECONDS

                    if farm_finish_time < int(time()):
                        logger.info(f"{self.session_name} | Claiming Farm balance")
                        await self.claim_farm(http_client=http_client, tg_web_data=tg_web_data)
                        await asyncio.sleep(randint(10, 20))
                        logger.info(f"{self.session_name} | Starting Farm")
                        await self.start_farm(http_client=http_client, tg_web_data=tg_web_data)
                    else:
                        farm_finish_in_seconds = farm_finish_time - int(time())
                        logger.info(f"{self.session_name} | Sleeping for {farm_finish_in_seconds}s")
                        await asyncio.sleep(farm_finish_in_seconds)

                except InvalidSession as error:
                    raise error
                except Exception as error:
                    logger.error(f"{self.session_name} | Unknown error: {error}")
                    await asyncio.sleep(10)


async def run_tapper(tg_client: Client, proxy: str | None):
    try:
        await Tapper(tg_client=tg_client).run(proxy=proxy)
    except InvalidSession:
        logger.error(f"{tg_client.name} | Invalid Session")

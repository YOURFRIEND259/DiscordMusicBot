import discord
from discord.ext import commands
import os
import asyncio
from youtubesearchpython import VideosSearch
from yt_dlp import YoutubeDL

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.help_message = self.generate_help_message()

    def generate_help_message(self):
        command_prefix = self.bot.command_prefix
        return f"""
General commands:
{command_prefix}help - wyswietla wszystkie komendy
{command_prefix}q - wyswietla kolejke
{command_prefix}p <tytul utworu/link> - odtwarza utwor z yt
{command_prefix}skip - pomija utwor
{command_prefix}clear - zatrzymuje muzyke i czysci kolejke
{command_prefix}stop - wyrzuca bota z kanalu
{command_prefix}pause - zatrzymuje utwor
{command_prefix}resume - wznawia odtwarzanie muzyki
{command_prefix}prefix - zmienia przedrostek komend
{command_prefix}remove - usuwa ostatni utwor z kolejki
"""

    @commands.Cog.listener()
    async def on_ready(self):
        await self.bot.change_presence(activity=discord.Game(f"type {self.bot.command_prefix}help"))

    @commands.command(name="help", help="wyswietla wszystkie komendy")
    async def help_command(self, ctx):
        await ctx.send(self.help_message)
    
    @commands.command(name="prefix", help="zmienia przedrostek komend")
    async def prefix(self, ctx, *args):
        self.bot.command_prefix = " ".join(args)
        self.help_message = self.generate_help_message()
        await ctx.send(f"Przedrostej zmieniono na **'{self.bot.command_prefix}'**")
        await self.bot.change_presence(activity=discord.Game(f"type {self.bot.command_prefix}help"))

class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.is_playing = False
        self.is_paused = False
        self.music_queue = []
        self.YDL_OPTIONS = {'format': 'bestaudio/best'}
        self.FFMPEG_OPTIONS = { 'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn', }
        self.vc = None
        self.ytdl = YoutubeDL(self.YDL_OPTIONS)

    def search_yt(self, item):
        if item.startswith("https://"):
            title = self.ytdl.extract_info(item, download=False)["title"]
            return {'source': item, 'title': title}
        search = VideosSearch(item, limit=1)
        return {'source': search.result()["result"][0]["link"], 'title': search.result()["result"][0]["title"]}

    async def play_next(self):
        if len(self.music_queue) > 0:
            self.is_playing = True
            m_url = self.music_queue[0][0]['source']
            self.music_queue.pop(0)
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: self.ytdl.extract_info(m_url, download=False))
            song = data['url']
            self.vc.play(discord.FFmpegPCMAudio(song, **self.FFMPEG_OPTIONS), after=lambda e: asyncio.run_coroutine_threadsafe(self.play_next(), self.bot.loop))
        else:
            self.is_playing = False

    async def play_music(self, ctx):
        if len(self.music_queue) > 0:
            self.is_playing = True
            m_url = self.music_queue[0][0]['source']
            if self.vc is None or not self.vc.is_connected():
                self.vc = await self.music_queue[0][1].connect()
                if self.vc is None:
                    await ctx.send("Nie da sie polaczyc")
                    return
            else:
                await self.vc.move_to(self.music_queue[0][1])
            self.music_queue.pop(0)
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: self.ytdl.extract_info(m_url, download=False))
            song = data['url']
            self.vc.play(discord.FFmpegPCMAudio(song, **self.FFMPEG_OPTIONS), after=lambda e: asyncio.run_coroutine_threadsafe(self.play_next(), self.bot.loop))
        else:
            self.is_playing = False

    @commands.command(name="play", aliases=["p", "playing"], help="odtwarza utwor z yt")
    async def play(self, ctx, *args):
        query = " ".join(args)
        try:
            voice_channel = ctx.author.voice.channel
        except:
            await ctx.send("musisz byc na kanale")
            return
        if self.is_paused:
            self.vc.resume()
        else:
            song = self.search_yt(query)
            if isinstance(song, bool):
                await ctx.send("nie udalo sie pobrac utworu")
            else:
                if self.is_playing:
                    await ctx.send(f"**#{len(self.music_queue)+2} -'{song['title']}'** Dodano do kolejki")  
                else:
                    await ctx.send(f"**'{song['title']}'** Dodano do kolejki")  
                self.music_queue.append([song, voice_channel])
                if not self.is_playing:
                    await self.play_music(ctx)

    @commands.command(name="pause", help="zatrzymuje utwor")
    async def pause(self, ctx, *args):
        if self.is_playing:
            self.is_playing = False
            self.is_paused = True
            self.vc.pause()
        elif self.is_paused:
            self.is_paused = False
            self.is_playing = True
            self.vc.resume()

    @commands.command(name="resume", aliases=["r"], help="wznawia odtwarzanie muzyki")
    async def resume(self, ctx, *args):
        if self.is_paused:
            self.is_paused = False
            self.is_playing = True
            self.vc.resume()

    @commands.command(name="skip", aliases=["s"], help="pomija utwor")
    async def skip(self, ctx):
        if self.vc is not None and self.vc:
            self.vc.stop()
            await self.play_music(ctx)

    @commands.command(name="queue", aliases=["q"], help="wyswietla kolejke")
    async def queue(self, ctx):
        retval = ""
        for i in range(len(self.music_queue)):
            retval += f"#{i+1} -" + self.music_queue[i][0]['title'] + "\n"
        if retval != "":
            await ctx.send(f"---Kolejka:\n{retval}---")
        else:
            await ctx.send("---Kolejka jest pusta---")

    @commands.command(name="clear", aliases=["c", "bin"], help="zatrzymuje muzyke i czysci kolejke")
    async def clear(self, ctx):
        if self.vc is not None and self.is_playing:
            self.vc.stop()
        self.music_queue = []
        await ctx.send("---Wyczyszczono kolejke---")

    @commands.command(name="stop", aliases=["disconnect", "l", "d"], help="wyrzuca bota z kanalu")
    async def disconnect(self, ctx):
        self.is_playing = False
        self.is_paused = False
        await self.vc.disconnect()

    @commands.command(name="remove", help="usuwa ostatni utwor z kolejki")
    async def remove(self, ctx):
        self.music_queue.pop()
        await ctx.send("usunieto ostatni utwor z kolejki")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

bot.remove_command('help')

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await setup(bot)

@bot.event
async def on_command_error(ctx, error):
    await ctx.send(f'Error: {str(error)}')

async def setup(bot):
    await bot.add_cog(MusicCog(bot))
    await bot.add_cog(HelpCog(bot))
bot.run('TOKEN')

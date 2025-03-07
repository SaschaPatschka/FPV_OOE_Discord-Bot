﻿import discord
import os
import asyncio
import requests
import datetime
import matplotlib.pyplot as plt
from io import BytesIO
import aiocron
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv #pip install python-dotenv


# .env-Dateien laden
load_dotenv("secrets.env")
load_dotenv("variables.env")

def get_env_int(var_name, default=0):
    value = os.getenv(var_name)
    return int(value) if value and value.isdigit() else default

VERSION = "1.3"
TOKEN = os.getenv("TOKEN")
GUILD_ID = get_env_int("GUILD_ID")  # Deine Server-ID
PRESENT_CHANNEL_ID = get_env_int("PRESENT_CHANNEL_ID")  # ID des Kanals, in dem der Bot aktiv sein soll
#CHANNEL_ID = 1259559371801886832  # Testchannel
ROLE_ID = get_env_int("ROLE_ID")  # ID der Rolle, die vergeben werden soll
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
ADMIN_CHANNEL_ID = get_env_int("ADMIN_CHANNEL_ID")
ADMIN_ROLE_ID = get_env_int("ADMIN_ROLE_ID")
MOD_ROLE_ID = get_env_int("MOD_ROLE_ID") 

# Discord-Client initialisieren
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
intents.message_content = True  # Wichtig für das Lesen von Nachrichten!

client = commands.Bot(command_prefix="",intents=intents)


######### EVENT HANDLING #########
@client.event
async def on_ready():
    print(f'✅ Bot ist online als {client.user}!')
    await client.tree.sync()  # Sicherstellen, dass die Slash-Commands auf Discord synchronisiert werden
    print("🌐 Slash-Commands wurden synchronisiert!")

     # Starte den Cron-Job für jeden Sonntag um 20 Uhr
    aiocron.crontab("0 20 * * SUN", func=verifyreport) #jeden Sonntag um 20 Uhr
    print("🕗 Cron-Job wurde gestartet!")


@client.event
async def on_message(message):
    if message.author.bot:
        return  # Ignoriere Bots
    
    print(f"New message: {message}")

    if message.channel.id != PRESENT_CHANNEL_ID:
        return  # Nur in dem gewünschten Kanal reagieren Kanal #new-vorstellungsrunde

    await handle_verification(message)

    await client.process_commands(message)  # Befehle weiterhin verarbeiten








######### SLASH-COMMANDS #########

# Slash-Command für Wetter
@client.tree.command(name="flugwetter", description="Zeigt das Flugwetter für eine Stadt an")
@app_commands.describe(stadt="Die Stadt, für die du das Wetter wissen willst (max. 5 Tage)", datum="Datum im Format 01.12.2025 oder 'morgen', 'übermorgen'")
async def flugwetter(interaction: discord.Interaction, stadt: str, datum: str = "heute"):
    await interaction.response.defer(ephemeral=True)
    #await interaction.followup.send(content="🔍 Suche nach Wetterdaten...")
    date_offset = 0
    if datum.lower() == "morgen":
        date_offset = 1
    elif datum.lower() == "übermorgen":
        date_offset = 2
    elif datum.lower() == "heute":
        date_offset = 0  # Heute
    else:
        try:
            date_obj = datetime.datetime.strptime(datum, "%d.%m.%Y").date()
            today = datetime.datetime.now(datetime.timezone.utc).date()
            date_offset = (date_obj - today).days
            if date_offset < 0:
                await interaction.followup.send(content="⚠️ Das Datum liegt in der Vergangenheit!", ephemeral=True)
                print(f"Wrong Date offset: {date_offset}")
                return
        except ValueError:
            await interaction.followup.send(content="⚠️ Ungültiges Datumsformat! Bitte nutze folgende Formate: `25.07.2025`, `morgen` oder `übermorgen`.", ephemeral=True)
            print(f"Wrong Date format: {datum}")
            return
    
    img_buf, weather_info = get_weather(stadt, date_offset)
    if img_buf:
        file = discord.File(img_buf, filename="weather.png")
        await interaction.followup.send(content=weather_info, file=file, ephemeral=True)
    else:
        await interaction.followup.send(content=weather_info, ephemeral=True)



# Prüft alle User, die sich noch nicht verifiziert haben und sendet eine Nachricht an den Admin-Channel mit einem kleinen Bericht
@client.tree.command(name="verifyreport", description="Schreibt einen Userreport in den Admin-Channel")
async def verifyreport(interaction: discord.Interaction):
    guild = interaction.guild
    #Admin-Channel
    channel = interaction.guild.get_channel(ADMIN_CHANNEL_ID)
    channel = interaction.client.get_channel(ADMIN_CHANNEL_ID)

    if channel is None:
        channel = await interaction.client.fetch_channel(ADMIN_CHANNEL_ID)

    #Wer hat den Befehl ausgeführt?
    member = interaction.user 

    if int(ADMIN_ROLE_ID) not in [role.id for role in member.roles] or int(MOD_ROLE_ID) not in [role.id for role in member.roles]:
        msg = await channel.send("Du hast keine Berechtigung für diesen Befehl!")
        await asyncio.sleep(10)  # Warte 10 Sekunden
        await msg.delete()  # Lösche die Nachricht

    unverifiedUsersStrings = []
    for member in guild.members:
        #Hat der User die Rolle?
        hat_rolle = False
        for role in member.roles:
            if role.id == int(ROLE_ID):
                hat_rolle = True
                break

        if not hat_rolle:
            unverifiedUsersStrings.append(f"'{member.name}' hat sich nicht verifiziert. Am Server seit: {member.joined_at}.")

    if unverifiedUsersStrings:
        bericht = "**📢 User, die sich noch nicht verifiziert haben:**\n" + "\n".join(unverifiedUsersStrings)
    else:
        bericht = "✅ Alle User erfüllen die Anforderungen!"

    #Falls der Bericht mehr als 1999 Zeichen hat, teile ihn in mehrere Nachrichten auf
    if len(bericht) > 1999:
        while len(bericht) > 1999:
            await channel.send(bericht[:1999])
            bericht = bericht[1999:]
        await channel.send(bericht)
    else:

        await channel.send(bericht)


@client.tree.command(name="info", description="Gibt Informationen über den Bot aus")
async def info(interaction: discord.Interaction):
    embed = discord.Embed(title="🤖 FPV OÖ Bot", description="Ein Discord-Bot für den FPV OÖ Server", color=0x00ff00)
    embed.add_field(name="Autor", value="Sascha Patschka (NoFear23m)", inline=False)
    embed.add_field(name="Contributors", value="Christoph Herbolzheimer (Christoph)", inline=False)
    embed.add_field(name="Version", value=VERSION, inline=False)
    embed.add_field(name="Github", value="https://github.com/SaschaPatschka/FPV_OOE_Discord-Bot", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


######### FUNCTIONS #########

async def handle_verification(message):
    guild = client.get_guild(GUILD_ID)
    member = guild.get_member(message.author.id)
    
    if ROLE_ID not in [role.id for role in member.roles]:  # Falls Rolle noch nicht vergeben
        if len(message.content) < 100:
            await send_temp_message(message.channel, f"Komm schon {message.author.mention}, erzähle doch ein bischen mehr von dir! Bitte bearbeite die Nachricht nochmal.")
            return  # Nur Nachrichten mit mindestens 100 Zeichen verarbeiten
        
        role = guild.get_role(ROLE_ID)
        await member.add_roles(role)
        msg = await message.channel.send(f"🎉 Super {message.author.mention}, du wurdest verifiziert und hast jetzt Zugriff auf alle Kanäle!")
        await message.add_reaction("👍")
        await asyncio.sleep(10)
        await msg.delete()
    else:
        await send_temp_message(message.channel, f"🚫 Hallo {message.author.mention}, dieser Kanal ist nicht zum Plaudern gedacht, bitte nutze einen anderen Kanal. Danke!")





# Sendet eine temporäre Nachricht in einen Kanal und löscht sie nach einer bestimmten Zeit
async def send_temp_message(channel, content, delay=10):
    msg = await channel.send(content)
    await asyncio.sleep(delay)
    await msg.delete()


# Wetter abrufen
def get_weather(city: str, date_offset=0):
    url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=de"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        forecast = data["list"]
        selected_date = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=date_offset)).date()

        # Sonnenaufgang & Sonnenuntergang (Zeitzone anpassen)
        city_timezone = datetime.timezone(datetime.timedelta(seconds=data["city"]["timezone"]))
        sunrise = datetime.datetime.fromtimestamp(data["city"]["sunrise"], tz=city_timezone)
        sunset = datetime.datetime.fromtimestamp(data["city"]["sunset"], tz=city_timezone)
        # Das Datum von Sonnenaufgang und Sonnenuntergang anpassen damit es mit dem ausgewählten Datum übereinstimmt
        sunrise = sunrise.replace(year=selected_date.year, month=selected_date.month, day=selected_date.day)
        sunset = sunset.replace(year=selected_date.year, month=selected_date.month, day=selected_date.day)
        
        # Wetterdaten für den ausgewählten Tag filtern
        daily_forecast = [
            entry for entry in forecast
            if selected_date == datetime.datetime.fromtimestamp(entry["dt"], tz=city_timezone).date()
        ]

        if not daily_forecast:
            return None, "⚠️ Keine Wetterdaten für dieses Datum verfügbar."

        best_time = None
        best_score = float(-100)  # Je höher der Score, desto besser
        temps, winds, rains, times = [], [], [], []

        for entry in daily_forecast:
            print(f'best_score: {best_score}')

            temp = entry["main"]["temp"]
            wind_speed = entry["wind"]["speed"]
            rain = entry.get("rain", {}).get("3h", 0)
            time_obj = datetime.datetime.fromtimestamp(entry["dt"], tz=city_timezone)
            time_str = time_obj.strftime("%H:%M")

            temps.append(temp)
            winds.append(wind_speed)
            rains.append(rain)
            times.append(time_str)

            # Bewertung berechnen (Priorität: Regen > Wind > Temperatur)
            if rain == 0:  # Kein Regen ist optimal
                wind_score = -wind_speed  # Niedriger Wind ist besser
                temp_score = -abs(temp - 25)  # Näher an 25°C ist besser
                total_score = wind_score + temp_score  # Gesamtbewertung
                #print(f'total_score for {time_str}: {total_score}!')

                if total_score > best_score and (time_obj > sunrise and time_obj < sunset):
                    best_score = total_score
                    best_time = time_str
                    #print(f'best_time set for {time_str} to {best_time}. Score: {best_score}!')

        # Diagramm erstellen
        plt.figure(figsize=(6, 4))
        plt.plot(times, temps, label="Temperatur (°C)", marker='o')
        plt.plot(times, winds, label="Wind (m/s)", marker='s')
        plt.plot(times, rains, label="Regen (mm)", marker='^')
        plt.xlabel("Uhrzeit")
        plt.ylabel("Werte")
        plt.legend()
        plt.title(f"Wettervorhersage für {city.capitalize()}")
        plt.xticks(rotation=45)
        plt.grid()

        img_buf = BytesIO()
        plt.savefig(img_buf, format='png')
        img_buf.seek(0)
        plt.close()

        # Ergebnistext erstellen
        best_flight_time = f"🕒 Beste Flugzeit: `{best_time}`" if best_time else "⚠️ Keine optimale Flugzeit gefunden."
        weather_report = (f"🌍 **Flugwetter in {city.capitalize()} am {selected_date}**\n"
                          f"🌅 Sonnenaufgang: `{sunrise.strftime('%H:%M')}`\n"
                          f"🌇 Sonnenuntergang: `{sunset.strftime('%H:%M')}`\n"
                          f"{best_flight_time}\n")
        return img_buf, weather_report

    return None, "⚠️ Konnte die Wetterdaten nicht abrufen. Stelle sicher, dass der Stadtname korrekt ist."
        




# Starte den Discord-Client
client.run(TOKEN)

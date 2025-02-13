import discord
import os
import asyncio
import requests
import datetime
import matplotlib.pyplot as plt
from io import BytesIO
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv #pip install python-dotenv


# .env-Dateien laden
load_dotenv("secrets.env")
load_dotenv("variables.env")

TOKEN = os.getenv("TOKEN")
GUILD_ID = os.getenv("GUILD_ID")  # Deine Server-ID
PRESENT_CHANNEL_ID = os.getenv("PRESENT_CHANNEL_ID")  # ID des Kanals, in dem der Bot aktiv sein soll
#CHANNEL_ID = 1259559371801886832  # Testchannel
ROLE_ID = os.getenv("ROLE_ID")  # ID der Rolle, die vergeben werden soll
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

# Discord-Client initialisieren
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
intents.message_content = True  # Wichtig für das Lesen von Nachrichten!

client = commands.Bot(command_prefix=None,intents=intents)




@client.event
async def on_ready():
    print(f'✅ Bot ist online als {client.user}!')
    await client.tree.sync()  # Sicherstellen, dass die Slash-Commands auf Discord synchronisiert werden

@client.event
async def handle_message(message):
    if message.author.bot:
        return  # Ignoriere Bots

    if message.channel.id != PRESENT_CHANNEL_ID:
        return  # Nur in dem gewünschten Kanal reagieren Kanal #new-vorstellungsrunde

    if len(message.content) < 100:
        msg = await message.channel.send(f"Komm schon {message.author.mention}, erzähle doch ein bischen mehr von dir! Bitte bearbeite die Nachricht nochmal.")

        await asyncio.sleep(10)  # Warte 10 Sekunden
        await msg.delete()  # Lösche die Nachricht
        return  # Nur Nachrichten mit mindestens 100 Zeichen verarbeiten

    guild = client.get_guild(GUILD_ID)
    member = guild.get_member(message.author.id)

    if ROLE_ID not in [role.id for role in member.roles]:  # Falls Rolle noch nicht vergeben
        role = guild.get_role(ROLE_ID)
        await member.add_roles(role)
        msg = await message.channel.send(f"🎉 Super {message.author.mention},du wurdest verifiziert und hast jetzt Zugriff auf alle Kanäle.!")

        await asyncio.sleep(10)  # Warte 10 Sekunden
        # Reagiere mit Daumen Hoch auf die Nachricht des Users
        await message.add_reaction("👍")
        await msg.delete()  # Lösche die Nachricht



# Slash-Command für Wetter
@client.tree.command(name="flugwetter", description="Zeigt das Flugwetter für eine Stadt an")
@app_commands.describe(stadt="Die Stadt, für die du das Wetter wissen willst (max. 5 Tage)", datum="Datum im Format 01.12.2025 oder 'morgen', 'übermorgen'")
async def flugwetter(interaction: discord.Interaction, stadt: str, datum: str = "heute"):
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
                await interaction.response.send_message("⚠️ Das Datum liegt in der Vergangenheit!", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("⚠️ Ungültiges Datumsformat! Bitte nutze: `01.12.2025`, `morgen` oder `übermorgen`.", ephemeral=True)
            return
    
    img_buf, weather_info = get_weather(stadt, date_offset)
    if img_buf:
        file = discord.File(img_buf, filename="weather.png")
        await interaction.response.send_message(weather_info, file=file)
    else:
        await interaction.response.send_message(weather_info)


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

        # Wetterdaten für den ausgewählten Tag filtern
        daily_forecast = [
            entry for entry in forecast
            if selected_date == datetime.datetime.fromtimestamp(entry["dt"], tz=city_timezone).date()
        ]

        if not daily_forecast:
            return None, "⚠️ Keine Wetterdaten für dieses Datum verfügbar."

        best_time = None
        best_score = float("-inf")  # Je höher der Score, desto besser

        temps, winds, rains, times = [], [], [], []

        for entry in daily_forecast:
            temp = entry["main"]["temp"]
            wind_speed = entry["wind"]["speed"]
            rain = entry.get("rain", {}).get("3h", 0)
            time_obj = datetime.datetime.fromtimestamp(entry["dt"], tz=city_timezone)

            # Nur Zeiten zwischen Sonnenaufgang und Sonnenuntergang berücksichtigen
            if time_obj < sunrise or time_obj > sunset:
                continue

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

                if total_score > best_score:
                    best_score = total_score
                    best_time = time_str

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

        

client.run(TOKEN)

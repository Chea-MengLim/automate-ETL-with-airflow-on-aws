

from airflow import DAG
from datetime import timedelta, datetime, timezone
from airflow.providers.http.sensors.http import HttpSensor
from airflow.providers.http.operators.http import SimpleHttpOperator
from airflow.operators.python import PythonOperator
import json
import pandas as pd
from dotenv import load_dotenv
import os


def kelvin_to_fahrenheit(temp_in_kelvin):
    return (temp_in_kelvin - 273.15) * 9/5 + 32


# Load environment variables
load_dotenv()
appid = os.getenv("WEATHERMAP_API_KEY")

def transform_load_data(task_instance):
    data = task_instance.xcom_pull(task_ids="extract_weather_data")

    city = data["name"]
    weather_description = data["weather"][0]['description']
    temp_fahrenheit = kelvin_to_fahrenheit(data["main"]["temp"])
    feels_like_fahrenheit = kelvin_to_fahrenheit(data["main"]["feels_like"])
    min_temp_fahrenheit = kelvin_to_fahrenheit(data["main"]["temp_min"])
    max_temp_fahrenheit = kelvin_to_fahrenheit(data["main"]["temp_max"])
    pressure = data["main"]["pressure"]
    humidity = data["main"]["humidity"]
    wind_speed = data["wind"]["speed"]
    time_of_record = datetime.fromtimestamp(data["dt"] + data["timezone"], tz=timezone.utc)
    sunrise_time = datetime.fromtimestamp(data["sys"]["sunrise"] + data["timezone"], tz=timezone.utc)
    sunset_time = datetime.fromtimestamp(data["sys"]["sunset"] + data["timezone"], tz=timezone.utc)

    transformed_data = {
        "City": city,
        "Description": weather_description,
        "Temperature (F)": temp_fahrenheit,
        "Feels Like (F)": feels_like_fahrenheit,
        "Minimum Temp (F)": min_temp_fahrenheit,
        "Maximum Temp (F)": max_temp_fahrenheit,
        "Pressure": pressure,
        "Humidity": humidity,
        "Wind Speed": wind_speed,
        "Time of Record": time_of_record,
        "Sunrise (Local Time)": sunrise_time,
        "Sunset (Local Time)": sunset_time
    }

    df = pd.DataFrame([transformed_data])

    aws_credentials = {
        "key": os.getenv("AWS_ACCESS_KEY_ID"),
        "secret": os.getenv("AWS_SECRET_ACCESS_KEY"),
        "token": os.getenv("AWS_SESSION_TOKEN"),
    }
    now = datetime.now()
    dt_string = now.strftime("current_weather_data_phnompenh_%d%m%Y%H%M%S")
    df.to_csv(f"s3://menglim/{dt_string}.csv", index=False, storage_options=aws_credentials)
    print(f"✅ Saved to: s3://menglim/{dt_string}.csv")


default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "start_date": datetime(2025, 7, 17),
    "email": ["menglimchea@gmail.com"],
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    "weather_dag",
    default_args=default_args,
    schedule_interval="@daily",
    catchup=False
) as dag:

    is_weather_api_ready = HttpSensor(
        task_id="is_weather_api_ready",
        http_conn_id="weathermap_api",
        endpoint=f"/data/2.5/weather?q=Phnom Penh&APPID={appid}"
    )

    extract_weather_data = SimpleHttpOperator(
        task_id="extract_weather_data",
        http_conn_id="weathermap_api",
        endpoint=f"/data/2.5/weather?q=Phnom Penh&APPID={appid}",
        method="GET",
        response_filter=lambda r: json.loads(r.text),
        log_response=True
    )

    transform_load_weather_data = PythonOperator(
        task_id="transform_load_weather_data",
        python_callable=transform_load_data
    )

    is_weather_api_ready >> extract_weather_data >> transform_load_weather_data

# 📊 IoT Time-Series Database Benchmarking (Docker + Python)

This project compares the performance of three time-series databases — **InfluxDB**, **TimescaleDB**, and **QuestDB** — using a Python script and Docker containers. It measures:

- 📈 Write throughput
- 🕒 Write and read latency
- 💿 Disk Usage
- 🧠 Memory usage
- 🧮 CPU usage

Useful for IoT sensor data evaluation in data-heavy time-series applications.

---

## 📦 Requirements

> 💡 This project was developed on WSL (Ubuntu), but you **don’t need WSL** if you're on **Windows** — you just need Docker and Python.

---

### 🪟 For Windows Users (No WSL)

1. **[Install Docker Desktop](https://www.docker.com/products/docker-desktop)**

   * Make sure Docker Engine and Docker Compose are running.
   * Docker Desktop comes with Docker Compose built-in.

2. **[Install Python 3.10 or newer](https://www.python.org/downloads/)**

   * Use the official Python installer for Windows.

3. **Install required Python packages**
   Open **Command Prompt** or **PowerShell**, then run:

   ```bash
   pip install requests psycopg2-binary docker
   ```

---

### 🐧 For WSL or Linux Users

1. **Install Docker Engine**
   Follow the [official Docker Engine installation guide](https://docs.docker.com/engine/install/) for your Linux distro.
   Make sure your user is in the `docker` group (or use `sudo`).

2. **Install Python 3.10+**
   Most modern Linux distros have Python preinstalled. To check:

   ```bash
   python3 --version
   ```

   If not installed, use your package manager (e.g., `sudo apt install python3`).

3. **Install required Python packages**

   ```bash
   pip3 install requests psycopg2-binary docker
   ```

---

## 🚀 How to Run the Benchmark

1. **Clone the repository and open the folder**

   ```bash
   git clone https://github.com/yapjayann/dbms_benchmark.git
   cd dbms_benchmark
   ```

2. **Start the databases**

   ```bash
   docker compose up 
   ```

   This launches:

   * 🐘 TimescaleDB (PostgreSQL)
   * 📈 InfluxDB 2.7
   * 🚀 QuestDB

3. **Open a new window in your terminal, run the benchmarking script in the same folder**

   ```bash
   cd dbms_benchmark
   python benchmark.py
   ```

4. **View the performance metrics in your terminal after benchmark.py finishes running**

5. **Stop the containers when done**

   ```bash
   docker compose down
   ```

---

## 📂 Project Structure

```
dbms_benchmark/
├── benchmark.py           # Python script to insert/query data and measure performance
├── docker-compose.yml     # Starts all 3 databases in containers
└── README.md              # You're reading this
```

---

## 📊 Example Output

```
=== Final Metrics ===

InfluxDB:
  write_throughput: 171.2045 records/s
  avg_write_latency: 0.0058 s
  read_latency: 0.0121 s
  disk_mb: 0.0039 MB
  cpu: 0.0882 %
  mem: 58363904.0000 bytes

TimescaleDB:
  write_throughput: 1102.1255 records/s
  avg_write_latency: 0.0009 s
  read_latency: 0.0027 s
  disk_mb: 0.0039 MB
  cpu: 0.4144 %
  mem: 158466048.0000 bytes

QuestDB:
  write_throughput: 237.4059 records/s
  avg_write_latency: 0.0042 s
  read_latency: 0.0126 s
  disk_mb: 0.0039 MB
  cpu: 8.9792 %
  mem: 530960384.0000 bytes
```

---

## 🧠 How It Works

* The script generates **dummy IoT sensor data** (temperature, humidity, etc.).
* It writes the data into each database using the appropriate protocol:

  * InfluxDB via **HTTP API**
  * TimescaleDB via **PostgreSQL**
  * QuestDB via **REST endpoint** 
* It then:

  * Measures write throughput (records per second)
  * Calculates average write latency per record
  * Measures read latency for retrieving inserted records
  * Monitors CPU and memory usage for each container
  * Tracks disk usage of each database after insertion

---

## 💬 Notes

* You can customize the number of records and test duration in `benchmark.py`.

---


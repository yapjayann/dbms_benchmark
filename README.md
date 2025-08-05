# 📊 IoT Time-Series Database Benchmarking (Docker + Python)

This project compares the performance of three time-series databases — **InfluxDB**, **TimescaleDB**, and **QuestDB** — using a Python script and Docker containers. It measures:

- 📈 Write throughput
- 🕒 Write and query latency
- ⏱️ Total write time
- 🧠 Memory usage
- 🧮 CPU usage

Useful for data evaluation in data-heavy time-series applications.

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
   pip install pandas
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
   pip3 install pandas
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
   python3 benchmark.py
   ```

4. **View the performance metrics in your terminal after benchmark.py finishes running**

5. **Stop the containers when done and delete volumes**

   ```bash
   docker compose down
   docker compose down -v
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
  write_throughput: 195.0083 records/s
  avg_write_latency: 0.0051 s
  total_write_time: 51.2799 s
  read_latency: 0.0243 s
  cpu: 0.0780 %
  mem: 79388672.0000 bytes

TimescaleDB:
  write_throughput: 2348.9885 records/s
  avg_write_latency: 0.0004 s
  total_write_time: 4.2572 s
  read_latency: 0.0024 s
  cpu: 0.5138 %
  mem: 80670720.0000 bytes

QuestDB:
  write_throughput: 419.6011 records/s
  avg_write_latency: 0.0024 s
  total_write_time: 23.8322 s
  read_latency: 0.0231 s
  cpu: 15.5710 %
  mem: 554917888.0000 bytes
```

---

## 🧠 How It Works

- The script loads **real, cleaned power consumption data** from `cleaned_power_data.csv` (sampled to `N = 1000` rows).
- It writes the data into each database using its respective ingestion method:

  - **InfluxDB**:
    - Uses the **native line protocol** over HTTP via direct `POST` requests.
    - Data is written one row at a time using precise timestamps (UNIX seconds).
    - Queried using the **Flux query language** (`Content-Type: application/vnd.flux`).

  - **TimescaleDB**:
    - Uses standard **PostgreSQL SQL inserts** via the `psycopg2` library.
    - All inserts are done in a loop and committed in bulk.
    - Queried using plain SQL (e.g., `SELECT * FROM power_data LIMIT 10`).

  - **QuestDB**:
    - Also uses the **PostgreSQL wire protocol** via `psycopg2`, not the REST API.
    - Offers high-ingestion performance using PostgreSQL-compatible SQL inserts.
    - Queried using SQL over the same PostgreSQL connection.

> ⚠️ QuestDB supports a REST API, but it’s not optimized for high-throughput ingest. This benchmark uses the PostgreSQL wire protocol instead for more consistent performance.

- For each database, the benchmark:

  - Measures **write throughput** (records per second)
  - Calculates **average write latency** (per row)
  - Measures **read latency** (for basic queries)
  - Monitors **CPU and memory usage** of each Docker container
  - Tracks **disk usage** after all records are written

---

## 💬 Notes

* You can customize the number of records written to each database by changing the N value in `benchmark.py`.

---




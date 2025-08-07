# 📊 IoT Time-Series Database Benchmarking (Docker + Python)

This project compares the performance of three time-series databases — **InfluxDB**, **TimescaleDB**, and **QuestDB** — using a Python script and Docker containers. It measures:

- 📈 Write throughput
- 🕒 Average write latency
- ⏱️ Total write time
- 🔍 Query latency (Full scan)
- 🔍 Query Latency (Aggregation)
- 🧠 Average Memory usage
- 🧮 Average CPU usage

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

## 🧼 Dataset Preprocessing

Before benchmarking, you need to generate a cleaned dataset from the original source.

1. **Download the original dataset**
   [UCI Individual Household Electric Power Consumption Dataset](https://archive.ics.uci.edu/dataset/235/individual+household+electric+power+consumption)

2. **Unzip it** and place `household_power_consumption.txt` in the project folder.

3. **Run the preprocessing script**
   This will clean and convert the data into `cleaned_power_data.csv`:

   ```bash
   python3 preprocess.py
   ```

> This cleaned CSV will then be used during benchmarking.

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
├── preprocess.py          # Cleans and transforms the raw power dataset, run this first
├── benchmark.py           # Python script to insert/query data and measure performance
├── docker-compose.yml     # Starts all 3 databases in containers
└── README.md              # You're reading this
```

---

## 📊 Example Output

```
Starting benchmarks...

--- InfluxDB ---

🕒 Cooling down before TimescaleDB test...


--- TimescaleDB ---

🕒 Cooling down before QuestDB test...


--- QuestDB ---


=== Final Metrics ===

📊 Benchmark Results for 100000 Records


InfluxDB:
  write_throughput: 966.6997 records/s
  avg_write_latency: 0.1372 s
  total_write_time: 103.4447 s
  read_latency: 0.0083 s
  agg_query_latency: 0.0068 s
  cpu: 21.4086 %
  mem: 579503340.3077 bytes

TimescaleDB:
  write_throughput: 1379.0252 records/s
  avg_write_latency: 0.0535 s
  total_write_time: 72.5150 s
  read_latency: 0.9952 s
  agg_query_latency: 0.6203 s
  cpu: 4.9794 %
  mem: 222076065.6842 bytes

QuestDB:
  write_throughput: 1052.9850 records/s
  avg_write_latency: 0.0007 s
  total_write_time: 94.9681 s
  read_latency: 0.0228 s
  agg_query_latency: 0.0284 s
  cpu: 25.0315 %
  mem: 1071793322.6667 bytes
```

---

## 🧠 How It Works

* The benchmark script loads **real, cleaned power consumption data** from `cleaned_power_data.csv` (sampled to `N` rows, modifiable in the script).
* It writes the data into each database using its respective ingestion method:

  - **InfluxDB**:
    - Uses the **native line protocol** over HTTP via batched `POST` requests.
    - Data is sent in **chunks of 1000 rows** with timestamps in **UNIX seconds**.
    - Queried using the **Flux query language**.

  - **TimescaleDB**:
    - Uses **batch inserts** with `psycopg2` and PostgreSQL syntax.
    - Rows are grouped in **batches of 1000** and inserted with a single SQL command.
    - Queried using plain SQL (e.g., `SELECT * FROM power_data`).

  - **QuestDB**:
    - Uses the **Influx Line Protocol over TCP** for fast ingestion.
    - Data is sent in **1000-row batches** with timestamps in **UNIX microseconds**.
    - Queried using SQL via a **PostgreSQL-compatible connection**.


- For each database, the benchmark:
  - Measures **write throughput** (records per second)
  - Calculates **average write latency** (per row)
  - Measures **read latency** (for full scan and aggregation)
  - Monitors **CPU and memory usage** of each Docker container for write/read operations

---

## 💬 Notes

* You can customize the number of records written to each database by changing the N value in `benchmark.py`.

---


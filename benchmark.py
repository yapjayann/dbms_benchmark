import time                     # For time measurements and delays
import requests                 # For making HTTP requests (InfluxDB)
import psycopg2                 # For PostgreSQL (TimescaleDB and QuestDB)
import docker                   # To monitor Docker container stats
from statistics import mean     # To compute average latencies, cpu and memory usage
from datetime import datetime   # For handling timestamps
import pandas as pd             # For data manipulation and reading CSV files
import threading                # For running container monitoring in the background
import socket                   # For sending data to QuestDB using ILP (InfluxDB Line Protocol)


# === Configuration ===

N = 100000  # Number of records extracted from dataset to insert in each database

# === Load Cleaned Data ===
csv_data = pd.read_csv("cleaned_power_data.csv")
csv_data = csv_data.sample(n=N, random_state=42).reset_index(drop=True)

# --- InfluxDB HTTP API endpoint and headers ---
INFLUX_URL = "http://localhost:8086/api/v2/write?org=myorg&bucket=mybucket&precision=s"
INFLUX_QUERY_URL = "http://localhost:8086/api/v2/query?org=myorg"
INFLUX_TOKEN = "mytoken"
INFLUX_HEADERS = {
    "Authorization": f"Token {INFLUX_TOKEN}",
    "Content-Type": "application/vnd.flux"  # Required for Flux query language
}

# --- TimescaleDB connection parameters ---
POSTGRES_CONFIG = {
    "dbname": "timeseries",
    "user": "postgres",
    "password": "postgres123",
    "host": "localhost",
    "port": 5432
}

# --- QuestDB connection parameters ---
QUESTDB_CONFIG = {
    "dbname": "qdb",
    "user": "admin",
    "password": "quest",
    "host": "localhost",
    "port": 8812
}

# Create a Docker client to collect container statistics
docker_client = docker.from_env()


# === Resource Monitor: Monitors CPU and memory usage of a specific Docker container ===
class ResourceMonitor:
    def __init__(self, container_name, interval=0.5):
        self.container_name = container_name
        self.interval = interval
        self.cpu_percents = []
        self.mem_usages = []
        self.running = False
        self.thread = None
        self.docker_client = docker.from_env()

    def _monitor(self):
        container = self.docker_client.containers.get(self.container_name)
        while self.running:
            stats1 = container.stats(stream=False)
            cpu_total_1 = stats1["cpu_stats"]["cpu_usage"]["total_usage"]
            sys_cpu_1 = stats1["cpu_stats"]["system_cpu_usage"]
            num_cpus = stats1["cpu_stats"].get("online_cpus", 1)
            mem_usage = stats1["memory_stats"]["usage"]
            time.sleep(self.interval)
            stats2 = container.stats(stream=False)
            cpu_total_2 = stats2["cpu_stats"]["cpu_usage"]["total_usage"]
            sys_cpu_2 = stats2["cpu_stats"]["system_cpu_usage"]
            cpu_delta = cpu_total_2 - cpu_total_1
            sys_delta = sys_cpu_2 - sys_cpu_1
            if sys_delta > 0.0 and cpu_delta > 0.0:
                cpu_percent = (cpu_delta / sys_delta) * num_cpus * 100.0
                self.cpu_percents.append(cpu_percent)
                self.mem_usages.append(mem_usage)

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._monitor)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread is not None:
            self.thread.join()
        avg_cpu = mean(self.cpu_percents) if self.cpu_percents else 0
        avg_mem = mean(self.mem_usages) if self.mem_usages else 0
        return avg_cpu, avg_mem
    
    def get_stats(self):
        avg_cpu = mean(self.cpu_percents) if self.cpu_percents else 0
        avg_mem = mean(self.mem_usages) if self.mem_usages else 0
        return avg_cpu, avg_mem




# === Get data from CSV ===
def get_csv_data(i): 
    row = csv_data.iloc[i]
    return {
        "timestamp": pd.to_datetime(row["timestamp"]),
        "gap": float(row["Global_active_power"]),
        "grp": float(row["Global_reactive_power"]),
        "voltage": float(row["Voltage"]),
        "intensity": float(row["Global_intensity"]),
        "sub_1": float(row["Sub_metering_1"]),
        "sub_2": float(row["Sub_metering_2"]),
        "sub_3": float(row["Sub_metering_3"])
    }


# === Benchmark for InfluxDB ===
def benchmark_influx():
    print("\n--- InfluxDB ---")
    monitor = ResourceMonitor("influxdb_dbms") # start monitoring InfluxDB container
    monitor.start()
    # === Start writing data to InfluxDB ===
    write_latencies = []
    start = time.time()
    batch_size = 1000
    lines = []

    for i in range(N):
        data = get_csv_data(i)

        ts = int(data["timestamp"].timestamp())  # Convert to UNIX timestamp
        # Create line protocol string for InfluxDB
        line = (
            f"power_data "
            f"global_active_power={data['gap']},"
            f"global_reactive_power={data['grp']},"
            f"voltage={data['voltage']},"
            f"global_intensity={data['intensity']},"
            f"sub_metering_1={data['sub_1']},"
            f"sub_metering_2={data['sub_2']},"
            f"sub_metering_3={data['sub_3']} "
            f"{ts}"
        )
        lines.append(line)

        # Measure batch write latency
        if len(lines) == batch_size:
            t0 = time.time()
            requests.post(INFLUX_URL, data="\n".join(lines), headers=INFLUX_HEADERS)
            write_latencies.append(time.time() - t0)
            lines = []

    # Final batch write if there are remaining lines
    if lines:
        t0 = time.time()
        requests.post(INFLUX_URL, data="\n".join(lines), headers=INFLUX_HEADERS)
        write_latencies.append(time.time() - t0)

    write_time = time.time() - start

    # Read latency: full table
    t0 = time.time()
    query = {
    "query": '''
    from(bucket: "mybucket")
    |> range(start: 0)
    |> filter(fn: (r) => r._measurement == "power_data")
    '''
    }
    requests.post(INFLUX_QUERY_URL, headers=INFLUX_HEADERS, json=query)

    read_latency = time.time() - t0


    # Aggregation query: hourly average of global_active_power
    t0 = time.time()
    agg_query = {
    "query": '''
    from(bucket: "mybucket")
    |> range(start: 0)
    |> filter(fn: (r) => r._measurement == "power_data" and r._field == "global_active_power")
    |> aggregateWindow(every: 1h, fn: mean)
    |> yield(name: "mean")
    '''
    
    }
    requests.post(INFLUX_QUERY_URL, headers=INFLUX_HEADERS, json=agg_query)
    agg_latency = time.time() - t0


    # === Stop Monitoring and Get Stats ===
    monitor.stop()
    cpu, mem = monitor.get_stats()
    
    # Return metrics
    return {
        "write_throughput": N / write_time,
        "avg_write_latency": mean(write_latencies),
        "total_write_time": write_time,
        "read_latency": read_latency,
        "agg_query_latency": agg_latency,
        "cpu": cpu,
        "mem": mem
    }

# === Benchmark for TimescaleDB ===
def benchmark_timescale():
    print("\n--- TimescaleDB ---")

    # Connect to TimescaleDB
    conn = psycopg2.connect(**POSTGRES_CONFIG)
    cur = conn.cursor()

    # Reset table
    cur.execute("DROP TABLE IF EXISTS power_data;")
    cur.execute("""
        CREATE TABLE power_data (
            timestamp TIMESTAMPTZ,
            global_active_power DOUBLE PRECISION,
            global_reactive_power DOUBLE PRECISION,
            voltage DOUBLE PRECISION,
            global_intensity DOUBLE PRECISION,
            sub_metering_1 DOUBLE PRECISION,
            sub_metering_2 DOUBLE PRECISION,
            sub_metering_3 DOUBLE PRECISION
        );
    """)

    conn.commit()

    # === Start monitoring TimescaleDB AFTER table creation ===
    monitor = ResourceMonitor("timescaledb_dbms") 
    monitor.start()
    # === Start writing data to TimescaleDB ===
    batch_size = 1000
    buffer = []
    write_latencies = []
    start = time.time()

    for i in range(N):
        data = get_csv_data(i)
        buffer.append((
            data["timestamp"], data["gap"], data["grp"], data["voltage"],
            data["intensity"], data["sub_1"], data["sub_2"], data["sub_3"]
        ))

        if len(buffer) == batch_size:
            t0 = time.time()
            args_str = ','.join(cur.mogrify("(%s,%s,%s,%s,%s,%s,%s,%s)", row).decode() for row in buffer)
            cur.execute(f"INSERT INTO power_data VALUES {args_str}")
            write_latencies.append(time.time() - t0)
            buffer = []

    if buffer:
        t0 = time.time()
        args_str = ','.join(cur.mogrify("(%s,%s,%s,%s,%s,%s,%s,%s)", row).decode() for row in buffer)
        cur.execute(f"INSERT INTO power_data VALUES {args_str}")
        write_latencies.append(time.time() - t0)

    conn.commit()
    write_time = time.time() - start

    # Read latency: full table
    t0 = time.time()
    cur.execute("SELECT * FROM power_data;")
    cur.fetchall()
    read_latency = time.time() - t0

    # Aggregation query: hourly average of global_active_power
    t0 = time.time()
    cur.execute("""
        SELECT date_trunc('hour', timestamp) AS hour,
               AVG(global_active_power)
        FROM power_data
        GROUP BY hour
        ORDER BY hour;
    """)
    cur.fetchall()
    agg_latency = time.time() - t0


    cur.close()
    conn.close()

    # === Stop Monitoring and Get Stats ===
    monitor.stop()
    cpu, mem = monitor.get_stats()

    # Return metrics
    return {
        "write_throughput": N / write_time,
        "avg_write_latency": mean(write_latencies),
        "total_write_time": write_time,
        "read_latency": read_latency,
        "agg_query_latency": agg_latency,
        "cpu": cpu,
        "mem": mem
    }




# === Benchmark for QuestDB ===
def benchmark_questdb():
    print("\n--- QuestDB (ILP over TCP) ---")

    # === Drop and recreate the table using SQL ===
    reset_conn = psycopg2.connect(**QUESTDB_CONFIG)
    reset_cur = reset_conn.cursor()
    reset_cur.execute("DROP TABLE IF EXISTS power_data;")
    reset_cur.execute("""
        CREATE TABLE power_data (
            timestamp TIMESTAMP,
            global_active_power DOUBLE,
            global_reactive_power DOUBLE,
            voltage DOUBLE,
            global_intensity DOUBLE,
            sub_metering_1 LONG,
            sub_metering_2 LONG,
            sub_metering_3 LONG
        ) timestamp(timestamp);
    """)
    reset_conn.commit()
    reset_cur.close()
    reset_conn.close()

    monitor = ResourceMonitor("questdb_dbms")
    monitor.start()
    # === Start writing data using ILP over TCP ===
    write_latencies = []
    batch_size = 1000
    lines = []
    start = time.time()

    # Helper function to send TCP payload to QuestDB
    def send_ilp_batch(batch_lines):
        payload = "\n".join(batch_lines).encode("utf-8")
        with socket.create_connection(("localhost", 9009)) as sock:
            sock.sendall(payload)

    for i in range(N):
        data = get_csv_data(i)
        ts = int(data["timestamp"].timestamp() * 1_000_000)  # microseconds

        # Embed timestamp as a field, not just as a trailing value
        line = (
            f"power_data,"
            f"timestamp={ts}i "  # Store timestamp as tag/field to match schema
            f"global_active_power={data['gap']},"
            f"global_reactive_power={data['grp']},"
            f"voltage={data['voltage']},"
            f"global_intensity={data['intensity']},"
            f"sub_metering_1={data['sub_1']}i,"
            f"sub_metering_2={data['sub_2']}i,"
            f"sub_metering_3={data['sub_3']}i "
            f"{ts}"
        )
        lines.append(line)

        if len(lines) == batch_size:
            t0 = time.time()
            send_ilp_batch(lines)
            write_latencies.append(time.time() - t0)
            lines = []

    if lines:
        t0 = time.time()
        send_ilp_batch(lines)
        write_latencies.append(time.time() - t0)

    write_time = time.time() - start

    # === Query using psycopg2 ===
    conn = psycopg2.connect(**QUESTDB_CONFIG)
    cur = conn.cursor()

    # Full table read
    t0 = time.time()
    cur.execute("SELECT * FROM power_data;")
    cur.fetchall()
    read_latency = time.time() - t0

    # Aggregation query
    t0 = time.time()
    cur.execute("""
        SELECT date_trunc('hour', timestamp) AS hour,
               AVG(global_active_power)
        FROM power_data
        GROUP BY hour
        ORDER BY hour;
    """)
    cur.fetchall()
    agg_latency = time.time() - t0

    cur.close()
    conn.close()

    monitor.stop()
    cpu, mem = monitor.get_stats()

    # Return metrics
    return {
        "write_throughput": N / write_time,
        "avg_write_latency": mean(write_latencies),
        "total_write_time": write_time,
        "read_latency": read_latency,
        "agg_query_latency": agg_latency,
        "cpu": cpu,
        "mem": mem
    }




# === Run All Benchmarks and Display Results ===
print("Starting benchmarks...")
results = {}

# InfluxDB
results["InfluxDB"] = benchmark_influx()

# Cooldown before next benchmark
print("\n🕒 Cooling down before TimescaleDB test...\n")
time.sleep(10)  # Cooldown to allow InfluxDB to stabilize

# TimescaleDB
results["TimescaleDB"] = benchmark_timescale()

# Cooldown before next benchmark
print("\n🕒 Cooling down before QuestDB test...\n")
time.sleep(10) # Cooldown to allow TimescaleDB to stabilize

# QuestDB
results["QuestDB"] = benchmark_questdb()




# === Final Results ===
print("\n\n=== Final Metrics ===")
print(f"\n📊 Benchmark Results for {N} Records\n")
for db, metrics in results.items():
    print(f"\n{db}:")
    for k, v in metrics.items():
        unit = (
            "s" if "latency" in k or "time" in k
            else "%" if k == "cpu"
            else "records/s" if "throughput" in k
            else "bytes"
        )
        print(f"  {k}: {v:.4f} {unit}")

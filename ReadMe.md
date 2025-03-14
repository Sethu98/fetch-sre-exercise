# Endpoint Monitoring agent

## Setting up

### Install python 3.13
I ran this on my Macbook with python 3.13. Since I'm unsure of version compatibility for the dependencies, please install python 3.13 to run this.
* For MacOS
  * download the installer from: https://www.python.org/downloads/release/python-3130/
* For Ubuntu
  * follow this guide: https://ubuntushell.com/install-python-beta-on-linux/

### Set up virtual environment
```bash
python3 -m venv .venv
```

### Activate the virtual environment
```bash
source .venv/bin/activate
```

### Install dependencies

```bash
pip install -r requirements.txt
```

## Running

```bash
python3 -m endpoint_monitor <Configuration File Path>

# Example
python3 -m endpoint_monitor test_files/test_config.yaml
```

## Change List
### 1. Use argparse
While using sys.argv works, adding extra options in the future would be cumbersome. 
I've built several command line tools with python before so when I saw the usage of sys.argv, I realised that using ArgumentParser would make it easier to read and extend.
So I refactored to use ArgumentParser instead. Now it would be easy to add arguments and new config options. For instance, we could make the time between consecutive checks configurable.
With argparse, it would be much easier add a new optional argument with a default value. I added a commented line to show this.

### 2. Use timeout in requests
The requirements state that response time must be <= 500ms for an endpoint to be considered healthy. The code does not handle that case. 
I'm using the timeout argument in the request method to satisfy this requirement.

### 3. Use multithreading
Since we could have multiple endpoints with each request taking upto 500ms (our timeout), doing it sequentially would be very slow. Since this is I/O bound, multi-threading would be pretty useful. 
So I modified the code to use `ThreadPoolExecutor` and send each request in a separate thread. I'm also using `as_completed` to process results as the futures get completed instead of waiting for all of them.
On measuring the time for 200 endpoints, I observed that sequential execution takes 62 seconds while multithreaded execution takes less than 5 seconds.

###  4. Introduce Endpoint class
I introduced a dataclass `Endpoint` to store information related to endpoints.
Now, we do not have to remember what the fields are and the class's constructor would do the key validation for us (meaning absence of required key and presence of an invalid key).

###  5. Introduce ConfigParser class
I created a new class `ConfigParser` to handle configuration file parsing. This contains validation for file's presence, parsing the YAML file and extracting endpoints. 
This handles all the parsing and related errors. It also makes it easier to add more file formats if needed and `extract_endpoints` would just give us the endpoints regardless of the file type.

### 6. Introduce EndpointMonitor class
I moved the endpoint monitoring code to the `EndpointMonitor` class. This class takes a list of endpoints in the constructor. It holds the endpoints and their related statistics together.
The `start_monitoring` method now does the actual monitoring. The initial code did the parsing and monitoring in the same function. I've separated the concerns here. 
`ConfigParser` will handle everything related to configuration. `EndpointMonitor` is responsible only for monitoring the given endpoints, and it doesn't care about how we got those endpoints.

### 7. Introduce Stats class
This class tracks all statistics. Currently, it's only domain level stats for how many endpoints are up. It'll hold all the stats so it's easy to extend and monitor other kind of statistics when needed.
For instance, we could monitor the average response time or the different status codes received.





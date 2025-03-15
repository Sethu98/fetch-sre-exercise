import argparse
import concurrent.futures
import dataclasses
import enum
import json
import pathlib
import time
from collections import defaultdict
from concurrent.futures.thread import ThreadPoolExecutor
from typing import List, Tuple, ClassVar
from urllib.parse import urlparse

import requests
import yaml
from yaml import YAMLError

DEFAULT_TIME_BW_CHECKS_SECS = 15


@dataclasses.dataclass
class Endpoint:
    name: str
    url: str
    method: str = 'GET'
    headers: dict = None
    body: str = None

    data_type_checks: ClassVar[List] = [('name', str), ('url', str), ('method', str), ('headers', dict), ('body', str)]

    def __post_init__(self):
        for attr_name, expected_type in self.data_type_checks:
            value = getattr(self, attr_name)
            if value is not None and not isinstance(value, expected_type):
                raise TypeError(f"{attr_name} must be of type {expected_type}")

    @property
    def domain(self):
        # If port is present, remove the port number
        return urlparse(self.url).netloc.split(':')[0]

    @property
    def json_body(self):
        return json.loads(self.body) if self.body else None


class HealthStatus(enum.Enum):
    UP = 1
    DOWN = 0


class InvalidConfigException(BaseException):
    pass


class ConfigParser:
    """
    Configuration file parser
    """

    @staticmethod
    def load_config(config_file_path: str):
        """
        Load the config file as array. Currently supports only .yaml files.

        :return: Array of dict, each representing an endpoint
        """
        path = pathlib.Path(config_file_path)
        if not path.exists():
            raise InvalidConfigException(f"Config file '{config_file_path}' does not exist")

        extension = path.suffix

        if extension == '.yaml':
            return ConfigParser.parse_yaml_config(config_file_path)
        # Add support for other extensions if required
        else:
            raise InvalidConfigException(f"Unsupported config file format: {extension}")

    @staticmethod
    def extract_endpoints(config_file_path: str) -> List[Endpoint]:
        """
        Parse the config file and extract the endpoints as Endpoint[].

        :raises: InvalidConfigException if the config file is invalid or if any of the endpoints have missing or invalid keys.
        """
        config = ConfigParser.load_config(config_file_path)
        endpoints = []

        for config_item in config:
            try:
                endpoints.append(Endpoint(**config_item))
            except TypeError as e:
                raise InvalidConfigException(f"Invalid endpoint configuration for {config_item}: {e}")

        return endpoints

    @staticmethod
    def parse_yaml_config(config_file_path: str):
        try:
            with open(config_file_path, 'r') as file:
                return yaml.safe_load(file)
        except YAMLError:
            raise InvalidConfigException("Config file is not a valid YAML file")


class Stats:
    """
    Tracks all required statistics
    """

    def __init__(self):
        self._domain_stats = defaultdict(lambda: {"up": 0, "total": 0})

    def record_domain_health(self, domain, status: HealthStatus):
        self._domain_stats[domain]["total"] += 1
        if status == HealthStatus.UP:
            self._domain_stats[domain]["up"] += 1

    def print_stats(self):
        print("Domain stats:")
        for domain, stats in self._domain_stats.items():
            availability = round(100 * stats["up"] / stats["total"])
            print(f"{domain} has {availability}% availability percentage")


class EndpointMonitor:
    """
    Orchestrates endpoint monitoring
    """

    def __init__(self, endpoints: List[Endpoint]):
        self._stats = Stats()
        self._endpoints = endpoints

    @staticmethod
    def check_health(endpoint: Endpoint) -> Tuple[str, HealthStatus]:
        """
        Check health of endpoint. Healthy if:
            * response status code is b/w 200 and 299
            * response time is less than 500ms
        :returns: (Domain, HealthStatus)
        """
        domain = endpoint.domain

        try:
            response = requests.request(endpoint.method, endpoint.url, headers=endpoint.headers,
                                        json=endpoint.json_body,
                                        timeout=0.5)

            if 200 <= response.status_code < 300:
                return domain, HealthStatus.UP
            else:
                return domain, HealthStatus.DOWN
        except requests.RequestException:
            return domain, HealthStatus.DOWN

    def check_all_endpoints(self):
        # Check health status for each endpoint with multiple threads
        # Each thread checks a single endpoint
        print(f"Requests started. Checking {len(self._endpoints)} endpoints.")
        start_time = time.time()
        futures = []

        with ThreadPoolExecutor() as executor:
            for endpoint in self._endpoints:
                futures.append(executor.submit(self.check_health, endpoint))

        for future in concurrent.futures.as_completed(futures):
            domain, health_status = future.result()
            self._stats.record_domain_health(domain, health_status)

        end_time = time.time()
        print(f"Completed processing requests in {round(end_time - start_time, 3)} seconds.\n")

    def start_monitoring(self, time_bw_checks_secs=DEFAULT_TIME_BW_CHECKS_SECS):
        """
        Monitor endpoints in a loop. Will not stop until the process is stopped.
        """
        while True:
            self.check_all_endpoints()

            # Log statistics
            self._stats.print_stats()

            print(f"---")
            time.sleep(time_bw_checks_secs)


def parse_cli_args():
    parser = argparse.ArgumentParser(prog="endpoints_monitor")
    parser.add_argument("config_file_path")
    # parser.add_argument("--time_bw_checks", required=False, default=DEFAULT_TIME_BW_CHECKS_SECS)

    return parser.parse_args()


def set_up_monitoring():
    cli_args = parse_cli_args()
    config_file_path = cli_args.config_file_path

    try:
        # Parse the config file and extract the endpoints
        endpoints = ConfigParser.extract_endpoints(config_file_path)

        # Start monitoring the endpoints
        endpoint_monitor = EndpointMonitor(endpoints)
        endpoint_monitor.start_monitoring()
    except InvalidConfigException as exp:
        print("Configuration error:", exp)
    except KeyboardInterrupt:
        print("\nMonitoring stopped by user")
    except Exception as e:
        print(f"Monitoring stopped due to an error: {e}")


# Entry point of the program
if __name__ == "__main__":
    set_up_monitoring()

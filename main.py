import argparse
import concurrent.futures
import dataclasses
import enum
import json
import pathlib
import sys
import time
from collections import defaultdict
from concurrent.futures.thread import ThreadPoolExecutor
from typing import List, Tuple
from urllib.parse import urlparse

import requests
import yaml
from yaml.parser import ParserError


@dataclasses.dataclass
class Endpoint:
    name: str
    url: str
    method: str = 'GET'
    headers: dict = None
    body: str = None

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
            raise InvalidConfigException(f"Error: Config file {config_file_path} does not exist")

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
                raise InvalidConfigException(f"Error: Invalid endpoint configuration for {config_item}: {e}")

        return endpoints

    @staticmethod
    def parse_yaml_config(config_file_path: str):
        try:
            with open(config_file_path, 'r') as file:
                return yaml.safe_load(file)
        except ParserError:
            InvalidConfigException("Error: Config file is not a valid YAML file")


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

    def __init__(self):
        self.stats = Stats()

    def check_health(self, endpoint: Endpoint) -> Tuple[str, HealthStatus]:
        domain = endpoint.domain

        try:
            response = requests.request(endpoint.method, endpoint.url, headers=endpoint.headers,
                                        json=endpoint.json_body,
                                        timeout=0.5)

            if 200 <= response.status_code < 300:
                return domain, HealthStatus.UP
            else:
                return domain, HealthStatus.DOWN
        except requests.RequestException as e:
            return domain, HealthStatus.DOWN

    # Main function to monitor endpoints
    def monitor_endpoints(self, endpoints: List[Endpoint]):
        while True:
            # Check health status for each endpoint with multiple threads
            # Since this is I/O bound, doing it sequentially is suboptimal.
            # So we use multi-threading to make it faster (GIL wouldn't be a problem here as this is I/O bound)
            futures = []

            with ThreadPoolExecutor() as executor:
                for endpoint in endpoints:
                    futures.append(executor.submit(self.check_health, endpoint))

            for future in concurrent.futures.as_completed(futures):
                domain, health_status = future.result()
                self.stats.record_domain_health(domain, health_status)

            # Log statistics
            self.stats.print_stats()

            print("---")
            time.sleep(15)


def parse_args():
    parser = argparse.ArgumentParser(prog="endpoints_monitor")
    parser.add_argument("config_file_path")

    return parser.parse_args()


def set_up_monitoring():
    cli_args = parse_args()
    config_file_path = cli_args.config_file_path

    try:
        # Parse the config file and extract the endpoints
        endpoints = ConfigParser.extract_endpoints(config_file_path)

        # Start monitoring the endpoints
        endpoint_monitor = EndpointMonitor()
        endpoint_monitor.monitor_endpoints(endpoints)
    except InvalidConfigException as exp:
        print(exp)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nMonitoring stopped by user")
    except Exception as e:
        print(f"Monitoring stopped due to an error: {e}")


# Entry point of the program
if __name__ == "__main__":
    set_up_monitoring()

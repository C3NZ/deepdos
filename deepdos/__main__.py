"""
    The main functionality of deepdos
"""
import os

import iptc

from deepdos.args import parse_args
from deepdos.conf import ROOT_DIR
from deepdos.data import load_model, parse_flow_data
from deepdos.firewall import Firewall
from deepdos.utils import (capture_pcap, examine_flow_packets,
                           execute_cicflowmeter)


class DeepDos:
    """
        The Deepdos executor and class manager
    """

    def __init__(self, options: dict):
        # Init data
        self.running = True
        self.model = load_model(options["model_type"])
        self.interface = options["interface"]
        self.interface_data = options["interface_data"]
        self.active_firewall = options["firewall"]

        # Predicitons file
        self.flow_file = open(f"{ROOT_DIR}/logs/flow_file.txt", "w+")

        # Setup the firewall
        if self.active_firewall:
            try:
                self.firewall = Firewall.create_firewall(
                    self.interface,
                    self.interface_data,
                    self.active_firewall,
                    options["naughty_count"],
                )
            except iptc.ip4tc.IPTCError:
                print("You need to be root in order to execute the program")

        else:
            self.firewall = None

    def capture_network_data(self):
        """
            Write pcap data
        """
        pcap_file = open(f"{ROOT_DIR}/pcap_info/out.pcap", "w", encoding="ISO-8859-1")
        pcap_list = capture_pcap(self.interface)

        # The counter controls the amount of writes that occur.
        print(f" - Writing packets to out.pcap file")
        pcap_file.writelines(pcap_list)
        pcap_file.close()

        print(" - Writing to csv")
        execute_cicflowmeter()

    def evaluate_network_data(self):
        """
            Load the flow data generated by the cicflowmeter, classify the flow data,
            and then take action with the firewall if needed.
        """
        try:
            flow_data = parse_flow_data()
        except ValueError:
            raise ValueError("too little flow")

        # Grab data out of model processor
        flow_features = flow_data["data"]
        flow_metadata = flow_data["metadata"]

        # Run model predictions
        result = self.model.predict(flow_features)
        proba = self.model.predict_proba(flow_features)

        # Flag Ip flow
        result_data = flow_metadata, result, proba
        malicious_flows, flow_logs = examine_flow_packets(result_data)
        print([flow for flow in malicious_flows])

        # If there is an active firewall, track all malicious flows
        if self.firewall:
            self.firewall.track_flows(malicious_flows)
        return flow_logs

    def main_loop(self):
        """
            Enter the main loop of the program, executing the sub processes
            and executing model commands
        """

        # Execute the main loop
        while self.running:
            try:
                # Capture network data and then evaluate it
                self.capture_network_data()
                flow_logs = self.evaluate_network_data()

                # Write to the flow file and remove the old pcap file
                self.flow_file.writelines(line + "\n" for line in flow_logs[0])
                self.flow_file.flush()
                os.remove(f"{ROOT_DIR}/pcap_info/out.pcap")

            except ValueError as exception:
                # Handle flow error
                if exception.args == "too little flow":
                    print(
                        " - Not enough information inside of generated flow, restarting process"
                    )
                continue


def start_execution():
    """
        Parse arguments and run our deepdos application
    """
    options = parse_args()
    DeepDos(options).main_loop()


if __name__ == "__main__":
    start_execution()

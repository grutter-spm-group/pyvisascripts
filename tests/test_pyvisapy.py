#!/usr/bin/env python3

#import pytest
import pyvisa


def test_pyvisapy_interface():
    """Simple test to validate linux-gpib is installed."""
    rm = pyvisa.highlevel.ResourceManager('@py')
    assert ('Available via Linux GPIB' in
            rm.visalib.get_debug_info()['GPIB INSTR'])

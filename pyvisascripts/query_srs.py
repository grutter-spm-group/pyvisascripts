#!/usr/bin/env python3

from pyvisa.highlevel import ResourceManager
from pyvisa.resources import GPIBInstrument
from typing import Optional, List, Final
from dataclasses import dataclass

from contextlib import contextmanager
import os

import fire


@contextmanager
def silence_glib_ctypes():
    """Silence unnecessary errors/warnings from glib_ctypes.

    Taken from: https://github.com/pyvisa/pyvisa-py/issues/282
    (credit goes to @tonyzzz321).
    """
    # stderr stream is linked to file descriptor 2, save a copy of the
    # real stderr so later we can restore it
    original_stderr = os.dup(2)
    # anything written to /dev/null will be discarded
    blackhole = os.open(os.devnull, os.O_WRONLY)
    # duplicate the blackhole to file descriptor 2,
    # which the C library uses as stderr
    os.dup2(blackhole, 2)
    # blackhole was duplicated from the line above,
    # so we don't need this anymore
    os.close(blackhole)
    yield
    # restoring the original stderr
    os.dup2(original_stderr, 2)
    os.close(original_stderr)


class VISAGenerics:
    """Holds generic pyvisa constants."""

    pyvisapy_cmd: Final[str] = '@py'
    gpib_id: Final[str] = 'GPIB'
    gpib_id_query: Final[str] = '*IDN?'


class SR830Params:
    """Constant parameters tied to SR830 device."""

    id: Final[str] = 'Stanford_Research_Systems,SR830,'
    end_of_str: Final[str] = '\n'
    attrib_separator: Final[str] = ','
    snap_request_str: Final[str] = 'SNAP?'
    snap_ids_range: Final[tuple] = (2, 6)


@dataclass
class SR830Attribute:
    """Holds an SR830 attribute (value + units).

    Args:
        name: name of the attribute.
        units: unit of the attribute.
        value: value of the attribute.
    """

    name: Final[str]
    units: Final[str]
    value: Optional[str] = None

    def __repr__(self):
        """Override dataclass repr for legibility."""
        return "%s: %s %s" % (self.name, self.value, self.units)


@dataclass
class SR830AttribMeta:
    """Holds aspects of different SR830 attributes.

    Args:
        units: indicates the uits of measurement that val is.
        snap_id: this attribute's ID in a SNAP query.
        query_str: the string for querying this attribute alone.
        requested: indicates whether this attribute has been
            requested to be queried.
    """

    units: Final[str]
    snap_id: Final[int]
    query_str: Final[Optional[str]] = None
    requested: bool = False


class SR830Communicator:
    """Helper class to communicate with SR830 and receive data.

    This class holds the different querying methods to receive
    data from the SR830 device. It can be used to request
    a series of attributes from the SR830, and will provide
    a list of results in response.

    Args:
        x: ... the x-value, in V.
        y: ... the y-value, in V.
        r: the r-value, in V.
        theta: ... the phase, in degrees.

        ref_freq: the reference frequency, in Hz.
        ch#: each of the channels, in whatever the display units are.
    """

    def __init__(self):
        """Construct, does not take any input args."""
        self.x = SR830AttribMeta(units='V', snap_id='1', query_str='OUTP?1')
        self.y = SR830AttribMeta(units='V', snap_id='2', query_str='OUTP?2')
        self.r = SR830AttribMeta(units='V', snap_id='3', query_str='OUTP?3')
        self.theta = SR830AttribMeta(units='deg', snap_id='4',
                                     query_str='OUTP?4')
        self.aux1 = SR830AttribMeta(units='V', snap_id='5', query_str='OAUX?1')
        self.aux2 = SR830AttribMeta(units='V', snap_id='6', query_str='OAUX?2')
        self.aux3 = SR830AttribMeta(units='V', snap_id='7', query_str='OAUX?3')
        self.aux4 = SR830AttribMeta(units='V', snap_id='8', query_str='OAUX?4')
        self.ref_freq = SR830AttribMeta(units='Hz', snap_id='9',
                                        query_str=None)
        self.ch1 = SR830AttribMeta(units='n/a', snap_id='10',
                                   query_str='OUTR?1')
        self.ch2 = SR830AttribMeta(units='n/a', snap_id='11',
                                   query_str='OUTR?2')

    def set_requested_data(self, provided_fields: List[str]):
        """Set the attributes we would like to obtain data on.

        Args:
            provided_fields: list of strings, with each being an attribute
                (e.g. 'x' for x attrib). If a provided value does not
                correspond to an attribute, we skip it.
        Returns:
            None.
        Raises:
            ???
        """
        for var in vars(self):
            current_attr = getattr(self, var)
            current_attr.requested = var in provided_fields
            setattr(self, var, current_attr)

    def get_query_list(self) -> List[str]:
        """Get list of queries to send to device.

        No input arguments are provided; the list of queries is created
        based on the attributes with requested=True (set them with
        set_requested_data()).

        Args:
            None.

        Returns:
            a list of gpib query strings, to be sent to the device

        Raises:
            ???
        """
        individual_queries = []
        snap_ids = []

        # Build up our queries (based on which attributes are
        # requested).
        for var in vars(self):
            current_attr = getattr(self, var)
            if current_attr.requested:
                if current_attr.query_str:
                    individual_queries.append(current_attr.query_str)
                snap_ids.append(current_attr.snap_id)

        if len(snap_ids) == 1 and len(individual_queries):
            # This should only happen in the case of res_freq,
            # which cannot be queried outside of a snap. Throw
            # an error.
            raise IOError("res_freq alone was requested, but can \
                only be provided bundled with other requests.")

        # If we have more than 1 request, bundle them into multiple
        # snap calls
        if len(snap_ids) > 1:
            individual_queries.clear()

            # Build up snap calls that fit the call size constraints
            num_ids_pre_query_creation = len(snap_ids)
            while num_ids_pre_query_creation >= SR830Params.snap_ids_range[0]:
                added_ids = 0
                query = SR830Params.snap_request_str

                # Build up each snap query to fit the 'ids range'
                # constraints: we need to ensure that each snap query
                # is within the min/max range of snap_ids_range.
                last_query_check = True
                queries_remaining_check = True
                while last_query_check or queries_remaining_check:
                    query += snap_ids.pop(0) + SR830Params.attrib_separator
                    added_ids += 1
                    last_query_check = (num_ids_pre_query_creation <=
                                        SR830Params.snap_ids_range[1]
                                        and snap_ids)
                    queries_remaining_check = (num_ids_pre_query_creation >
                                               SR830Params.snap_ids_range[1] and
                                               (len(snap_ids) %
                                                SR830Params.snap_ids_range[1] >=
                                                SR830Params.snap_ids_range[0]))

                # Once we have a snap query ready, add it to our list
                individual_queries.append(query)
                num_ids_pre_query_creation = len(snap_ids)
        return individual_queries

    def parse_responses(self, query_responses: List[str]
                        ) -> List[SR830Attribute]:
        """Parse the response(s) received from a provided list of queries.

        Args:
            query_responses: the response(s) received from the SR830 device

        Returns:
            A list of SR830Attributes.

        Raises:
            - IndexError, if len(query_results) != len(vars(self)) with
                requested==True (this implies a mismatch between query
                creation and response).
        """
        # Parse the response(s) by splitting into individual data results
        # (i.e. going from a List of response strings to a List of floats)
        results = []
        for response in query_responses:
            for value in response.split(SR830Params.attrib_separator):
                results.append(value)

        # Create a list of SR830Attributes containing these values
        attributes = []
        for var in vars(self):
            current_attr = getattr(self, var)

            if current_attr.requested:
                attr = SR830Attribute(name=var,
                                      value=results.pop(0),
                                      units=current_attr.units)
                attributes.append(attr)

        # Confirm that there are no extra results, as this would imply
        # a mismatch between query creation and response.
        if results:
            raise IOError("The query creation and response do not match!")

        return attributes


def connect_to_device(force_pyvisapy: bool = False, visa_lib_path: str = ''
                      ) -> Optional[GPIBInstrument]:
    """Connect to the SR830 instrument and returns its object.

    Args:
        force_pyvisapy: bool, we force the pyvisa-py backend if True
        visa_lib_path: an optional string path to the visa library

    Returns:
        A GPIBInstrument instance of the connected instrument, or None
            upon failure.

    Raises:
        ???
    """
    with silence_glib_ctypes():
        rm_args = (VISAGenerics.pyvisapy_cmd if force_pyvisapy
                   else visa_lib_path)

        rm = ResourceManager(rm_args)

        for instr_id in rm.list_resources():
            if VISAGenerics.gpib_id in instr_id:
                instr = rm.open_resource(instr_id)
                if SR830Params.id in instr.query(VISAGenerics.gpib_id_query):
                    return instr

        # The SP-830 was not found!
        return None


def query_device(device: GPIBInstrument, desired_attribs: List[str]
                 ) -> List[SR830Attribute]:
    """Query SR830 device for attributes.

    Args:
        device: GPIBInstrument instance corresponding to SR830.
        desired_atribs: list of strings, with each corresponding to
            the attribute of interest.

    Returns:
        List of SR830Attribute, corresponding to the requested
            attributes's reported values (and units).
    Raises:
        ???
    """
    communicator = SR830Communicator()
    communicator.set_requested_data(desired_attribs)
    queries = communicator.get_query_list()

    responses = []
    for query in queries:
        response = device.query(query).split(SR830Params.end_of_str)[0]
        responses.append(response)

    return communicator.parse_responses(responses)


def connect_and_query_device(desired_attribs: List[str],
                             visa_lib_path: str = '',
                             force_pyvisapy: bool = False,
                             ) -> List[SR830Attribute]:
    """Connect to SR830 and query for attributes.

    Args:
        desired_attribs: list of strings, with each corresponding to
            the attribute of interest. For example, for attributes
            x and y, provide ['x', 'y'].
        visa_lib_path: an optional string path to the visa library.
        force_pyvisapy: bool, we force the pyvisa-py backend if True.

    Returns:
        List of SR830Attribute, corresponding to the requested
            attributes's reported values (and units).
    Raises:
        ???
    """
    device = connect_to_device(force_pyvisapy, visa_lib_path)
    if device:
        return query_device(device, desired_attribs)
    else:
        print('Device not found, exiting.')


if __name__ == '__main__':
    fire.Fire(connect_and_query_device)

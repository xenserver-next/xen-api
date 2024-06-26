#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This module provides unittest for hfx_filename
"""

import sys
import unittest
from mock import MagicMock, patch, call
from python3.tests.import_helper import import_file_as_module

# mock modules to avoid dependencies
sys.modules["XenAPI"] = MagicMock()

hfx_filename = import_file_as_module("python3/bin/hfx_filename")


@patch("socket.socket")
class TestRpc(unittest.TestCase):
    """
    This class tests blow functions:
    rpc()
    db_get_uuid()
    read_field()
    """
    def test_rpc(self, mock_socket):
        """
        Tests rpc
        """
        mock_connected_socket = MagicMock()
        mock_socket.return_value = mock_connected_socket

        recv_data = b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\nHelloWorld"
        # Set the return value for the first call to recv
        mock_connected_socket.recv.side_effect = [recv_data, None]

        session_id = 0
        request = "socket request"
        body = hfx_filename.rpc(session_id, request)

        # Assert that the socket methods were called as expected
        expected_data = [
            b"POST /remote_db_access?session_id=0 HTTP/1.0\r\n",
            b"Connection:close\r\n",
            b"content-length:14\r\n",
            b"\r\n",
            b"socket request"
        ]
        mock_connected_socket.send.assert_has_calls([call(data) for data in expected_data])

        expected_return = "HelloWorld"
        self.assertEqual(expected_return, body)

    def test_rpc_international_character(self, mock_socket):
        """
        Tests rpc using non-ascii characters
        """
        mock_connected_socket = MagicMock()
        mock_socket.return_value = mock_connected_socket

        recv_data = b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\nHelloWorld"
        # Set the return value for the first call to recv
        mock_connected_socket.recv.side_effect = [recv_data, None]

        session_id = 0
        # Use international character"socket 请求" as request
        request = "socket 请求"
        body = hfx_filename.rpc(session_id, request)

        # Assert that the socket methods were called as expected
        expected_data = [
            b"POST /remote_db_access?session_id=0 HTTP/1.0\r\n",
            b"Connection:close\r\n",
            b"content-length:13\r\n",
            b"\r\n",
            request.encode('utf-8')
        ]
        mock_connected_socket.send.assert_has_calls([call(data) for data in expected_data])

        expected_return = "HelloWorld"
        self.assertEqual(expected_return, body)

    def test_db_get_uuid(self, mock_socket):
        """
        Tests db_get_uuid
        """
        mock_connected_socket = MagicMock()
        mock_socket.return_value = mock_connected_socket

        header = "HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\n"
        body = ("<value><array><data><value>success</value><value>HelloWorld"
                "</value></data></array></value>")
        recv_data = (header + body).encode('utf-8')
        # Set the return value for the first call to recv
        mock_connected_socket.recv.side_effect = [recv_data, None]

        expected_response = "HelloWorld"
        response = hfx_filename.db_get_by_uuid(0, "pool_patch", "22345")
        self.assertEqual(expected_response, response)

    def test_read_field(self, mock_socket):
        """
        Tests read_field
        """
        mock_connected_socket = MagicMock()
        mock_socket.return_value = mock_connected_socket

        header = "HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\n"
        body = ("<value><array><data><value>success</value><value>file_name"
                "</value></data></array></value>")
        recv_data = (header + body).encode('utf-8')
        # Set the return value for the first call to recv
        mock_connected_socket.recv.side_effect = [recv_data, None]

        expected_filename = "file_name"
        filename = hfx_filename.read_field(0, "pool_patch", "filename", "rf")
        self.assertEqual(expected_filename, filename)


class TestParse(unittest.TestCase):
    """
    This class tests function parse_string()
    """
    def test_parse_string(self):
        """
        Tests parse_string
        """
        txt = ("<value><array><data><value>success</value><value>abcde"
               "</value></data></array></value>")
        expected_txt = "abcde"
        return_txt = hfx_filename.parse_string(txt)
        self.assertEqual(expected_txt, return_txt)

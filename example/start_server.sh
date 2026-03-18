#!/usr/bin/env bash

action() {
    histserv-server --port 50051 --n-threads 4
}
action "$@"

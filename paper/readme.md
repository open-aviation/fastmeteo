# Introduction

This repository accompanies the paper "Fast Contrail Estimation with OpenSky Data", providing Python notebooks, scripts, and datasets integral to this paper and its findings.

## Python Notebooks and Scripts

- `plot.ipynb`: This Jupyter notebook contains the code to replicate the figures presented in the paper.
- `benchmark.ipynb`: This Jupyter notebook demonstrates the benchmarking process of the `fastmeteo` library, showcasing its performance with different flights.
- `contrail.py`: A Python script that includes all necessary functions for contrail estimation, as discussed in the paper.

## Data Files

- `example_flight.csv`: This file contains an example flight dataset, used in the paper to demonstrate plot generation.
- `eham_flights_benchmark.csv.gz`: A compressed CSV file with flight trajectory data. It is used to benchmark the `fastmeteo` library's performance.
- `benchmark_results.csv`: Benchmarking results for individual flights, providing key data for the creation of Figure 5 in the paper.

## Installation Note

To reproduce the results presented, it is necessary to install the `fastmeteo` Python library. Installation instructions and additional information are available at: https://github.com/junzis/fastmeteo

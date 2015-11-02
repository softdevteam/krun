#!/usr/bin/env python2.7
"""
usage:
    results2csv.py <json results file>
"""

import bz2, csv, json, sys


def usage():
    print(__doc__)
    sys.exit(1)


def make_csv_filename(benchmark):
    return benchmark.replace(':', '_') + '.csv'


def main(data_dct):
    results = data_dct['data']
    for benchmark in results:
        fname = make_csv_filename(benchmark)
        iterations = len(results[benchmark][0])
        with open(fname, 'w') as csvfile:
            zipped = zip(*results[benchmark])
            writer = csv.writer(csvfile)
            for index in range(iterations):
                writer.writerow(zipped[index])


def read_results_file(results_file):
    results = None
    with bz2.BZ2File(results_file, "rb") as f:
        results = json.loads(f.read())
    return results


if __name__ == '__main__':
    try:
        json_file = sys.argv[1]
    except IndexError:
        usage()
    data_dct = read_results_file(json_file)
    main(data_dct)

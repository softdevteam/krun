#!/usr/bin/env python2.7
"""
usage:
    mk_graphs.py <config file>
"""

import sys
import json
import random
import statsmodels.api as sm
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from statsmodels.tsa.stattools import acf
from matplotlib.widgets import Slider, Button

plt.style.use('ggplot')

# Set figure size for plots
plt.figure(tight_layout=True)

# Set font size
font = {
    'family' : 'sans',
    'weight' : 'regular',
    'size'   : '12',
}
matplotlib.rc('font', **font)

INITIAL_DECOMP_FREQ = 4
INITIAL_LAG = 5
BINS = 200

SLIDER_COLOUR = "lightgoldenrodyellow"

# We must hold references to these or they get GC'd and cause issues
DECOMP_SLIDERS = []
LAG_SLIDERS = []

DECOMP_TYPE_SEASONS = 0
DECOMP_TYPE_TREND = 1


def usage():
    print(__doc__)
    sys.exit(1)

def chop_warmups(executions, warmup):
    chopped = [x[warmup:] for x in executions]

    if len(chopped) == 0:
        print("no data after warmup")
        sys.exit(1)

    return chopped


def main(config, config_filename, data_dct):
    n_graphs = config["N_GRAPHS_PER_BENCH"]

    # Iterate over keys in the json file drawing some graphs
    keys = sorted(data_dct["data"].keys())
    for key in keys:
        bench, vm, variant = key.split(":")
        warmup = config["VMS"][vm]["warm_upon_iter"]
        executions = data_dct["data"][key]
        executions = chop_warmups(executions, warmup)
        all_exec_nums = range(len(executions))
        random.shuffle(all_exec_nums)
        chosen_exec_nums = all_exec_nums[0:n_graphs]
        interactive(key, executions, chosen_exec_nums)


def lag_xs(data, lag):
    return [data[x-lag] for x in range(len(data))]


def draw_runseq_subplot(axis, data):
    axis.plot(data)
    axis.set_title("Run Sequence")
    axis.set_xlabel("Iteration")
    axis.set_ylabel("Time(s)")


def draw_acr_subplot(axis, data):
    vals = acf(data, nlags=len(data) / 2, unbiased=True)
    axis.plot(vals)
    axis.set_title("Unbiased ACR")
    axis.set_xlabel("Lag")
    axis.set_ylabel("Correlation")


def draw_decomp_subplot(axis, data, freq, which, with_slider=False):
    if with_slider:
        sldr_ax = plt.axes([0.1, 0.02, 0.28, 0.03], axisbg=SLIDER_COLOUR)
        sldr = Slider(sldr_ax, 'Freq', 1, 100, valinit=freq, valfmt='%d')
        DECOMP_SLIDERS.append(sldr)

    def do_draw(axis, data, freq):
        freq = int(freq)
        axis.clear()
        sd = sm.tsa.seasonal_decompose(data, freq=freq)

        if which == DECOMP_TYPE_SEASONS:
            vals = sd.seasonal
            title = "Seasons"
        elif which == DECOMP_TYPE_TREND:
            vals = sd.trend
            title = "Trend"
        else:
            assert False  # unreachable

        axis.plot(vals)
        axis.set_title(title)
        axis.set_xlabel("Iteration")
        axis.set_ylabel("Time(s)")

    def update(val):
        new_freq = sldr.val
        do_draw(axis, data, new_freq)

    if with_slider:
        sldr.on_changed(update)

    do_draw(axis, data, freq)


def draw_lag_subplot(axis, data, lag, with_slider=False):
    if with_slider:
        sldr_ax = plt.axes([0.2, 0.02, 0.3, 0.03], axisbg=SLIDER_COLOUR)
        sldr = Slider(sldr_ax, 'Lag', 1, 100, valinit=lag, valfmt='%d')
        LAG_SLIDERS.append(sldr)

    def do_draw(axis, data, lag):
        axis.clear()
        lag = int(lag)
        xs = lag_xs(data, lag)
        axis.set_title("Lag %d" % lag)
        axis.plot(xs, data, 'rx')

    def update(val):
        newlag = sldr.val
        do_draw(axis, data, newlag)

    if with_slider:
        sldr.on_changed(update)

    do_draw(axis, data, lag)


def zoom_on_runseq(data):
    fig, ax = plt.subplots(1, 1, squeeze=False)
    draw_runseq_subplot(ax[0, 0], data)
    fig.show()


def zoom_on_lag(data, lag):
    fig, ax = plt.subplots(1, 1, squeeze=False)
    draw_lag_subplot(ax[0, 0], data, lag, with_slider=True)
    fig.show()


def zoom_on_acr(data):
    fig, ax = plt.subplots(1, 1, squeeze=False)
    draw_acr_subplot(ax[0, 0], data)
    fig.show()


def zoom_on_decomp(data, freq, which):
    fig, ax = plt.subplots(1, 1, squeeze=False)
    draw_decomp_subplot(ax[0, 0], data, freq, which, with_slider=True)
    fig.show()


def zoom_on_hist(data):
    fig, ax = plt.subplots(1, 1, squeeze=False)
    draw_hist_subplot(ax[0, 0], data)
    fig.show()


def draw_hist_subplot(axis, data):
    axis.hist(data, bins=BINS)
    axis.set_title("Histogram")
    axis.set_xlabel("Time(x)")
    axis.set_ylabel("Frequency")


def interactive(key, executions, chosen_exec_nums): # XXX one exec for now
    # clear old sliders
    del(LAG_SLIDERS[:])
    del(DECOMP_SLIDERS[:])

    n_execs = len(chosen_exec_nums)
    fig, axes = plt.subplots(n_execs, 6, squeeze=False)

    buttons = [] # must hold refs, or they die
    col = 0

    def mk_runseq_cb(data):
        def f(label):
            zoom_on_runseq(data)
        return f

    def mk_lag_cb(data, lag):
        def f(label):
            zoom_on_lag(data, lag)
        return f

    def mk_hist_cb(data):
        def f(label):
            zoom_on_hist(data)
        return f

    def mk_acr_cb(data):
        def f(label):
            zoom_on_acr(data)
        return f

    def mk_decomp_cb(data, freq, which):
        def f(label):
            zoom_on_decomp(data, freq, which)
        return f

    # run seq
    for idx in range(n_execs):
        data = executions[idx]
        but = Button(axes[idx, col], "")
        axes[idx, col].axis(aspect="equal")
        buttons.append(but)
        but.on_clicked(mk_runseq_cb(data))
        draw_runseq_subplot(axes[idx, col], data)
    col += 1

    # lag
    for idx in range(n_execs):
        data = executions[idx]
        draw_lag_subplot(axes[idx, col], data, INITIAL_LAG)
        but = Button(axes[idx, col], "")
        buttons.append(but)
        but.on_clicked(mk_lag_cb(data, INITIAL_LAG))

    col += 1

    # histogram
    for idx in range(n_execs):
        data = executions[idx]
        but = Button(axes[idx, col], "")
        buttons.append(but)
        but.on_clicked(mk_hist_cb(data))
        draw_hist_subplot(axes[idx, col], data)
    col += 1

    # ACR
    for idx in range(n_execs):
        data = executions[idx]
        but = Button(axes[idx, col], "")
        buttons.append(but)
        but.on_clicked(mk_acr_cb(data))
        draw_acr_subplot(axes[idx, col], data)
    col += 1

    freq = INITIAL_DECOMP_FREQ
    # seasonal decomposition: seasons
    for idx in range(n_execs):
        data = executions[idx]
        but = Button(axes[idx, col], "")
        buttons.append(but)
        but.on_clicked(mk_decomp_cb(data, freq, DECOMP_TYPE_SEASONS))
        draw_decomp_subplot(axes[idx, col], data, freq, DECOMP_TYPE_SEASONS)
    col += 1

    # seasonal decomposition: trend
    for idx in range(n_execs):
        data = executions[idx]
        but = Button(axes[idx, col], "")
        buttons.append(but)
        but.on_clicked(mk_decomp_cb(data, freq, DECOMP_TYPE_TREND))
        draw_decomp_subplot(axes[idx, col], data, freq, DECOMP_TYPE_TREND)
    col += 1

    fig.suptitle("Overview -- %s -- executions %s" % (key, repr(chosen_exec_nums)))
    mng = plt.get_current_fig_manager()
    mng.resize(*mng.window.maxsize())
    plt.show()

if __name__ == "__main__":
    from krun.util import read_config, output_name
    try:
        cfile = sys.argv[1]
    except IndexError:
        usage()

    json_file, config = output_name(cfile), read_config(cfile)

    with open(json_file, "r") as fh:
        data_dct = json.load(fh)

    plt.close() # avoid extra blank window
    main(config, sys.argv[1], data_dct)

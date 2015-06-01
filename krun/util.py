def should_skip(config, this_key):
    skips = config.SKIP

    for skip_key in skips:
        skip_elems = skip_key.split(":")
        this_elems = this_key.split(":")

        # should be triples of: bench * vm * variant
        assert len(skip_elems) == 3 and len(this_elems) == 3

        for i in range(3):
            if skip_elems[i] == "*":
                this_elems[i] = "*"

        if skip_elems == this_elems:
            return True # skip

    return False

def read_config(config_file):
    import_name = config_file[:-3]
    out_file = import_name + "_results.json"
    try:
        config = __import__(import_name)
    except:
        print("*** error importing config file!\n")
        raise

    return import_name, config

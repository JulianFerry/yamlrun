import argparse
from .yaml import Yaml


def parse_args():
    """
    Load the YAML file path as a positional argument

    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'yaml',
        metavar='yaml path',
        type=str,
        nargs=1,
        help='The yaml file to parse'
    )
    parser.add_argument(
        '-q',
        action='store_true',
        help='Quiet mode'
    )
    parser.add_argument(
        '--noenv',
        action='store_true',
        help='Whether to look for variables in environment values'
    )
    args = parser.parse_args().__dict__
    yaml_path = args['yaml'][0]
    quiet = args['q']
    noenv = args['noenv']
    return yaml_path, quiet, noenv


def run():
    """
    Load variables from YAML file and run script

    """
    args = parse_args()
    yaml = Yaml(*args)
    yaml.parse_structure()
    yaml.parse_variables()
    yaml.run_script()


if __name__ == "__main__":
    run()
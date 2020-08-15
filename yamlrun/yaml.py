import os
import re
import json
import shlex
import subprocess

from yaml import safe_load
from yaml.parser import ParserError
from tabulate import tabulate
from pprint import pprint


class Yaml(dict):
    """
    YAML file object

    Parameters
    ----------
    path: str
        Path to YAML file passed as a command-line argument by the user
    quiet: bool
        Run all commands quietly (except script execution)
    noenv: bool
        Whether to fetch $variables from the environment

    """
    def __init__(
        self,
        path: str,
        quiet: bool=False,
        noenv: bool=False
    ):
        """
        Parse YAML file
        """
        self.path = path
        self.quiet = quiet
        self.noenv = noenv
        if not os.path.exists(path):
            raise ValueError(f'File does not exist: {path}')
        with open(path, 'r') as stream:
            try:
                super().__init__(safe_load(stream))
            except TypeError:
                raise ParserError("yaml file is empty")

    def print(self, *args):
        """
        Verbose print: does not print if self.quiet is True
        """
        if not self.quiet:
            print(*args)

    def pprint(self, *args, **kwargs):
        """
        Verbose pretty print: does not print if self.quiet is True
        """
        if not self.quiet:
            pprint(*args, **kwargs)
            print('\n')

    def parse_structure(
        self
    ):
        """
        Load YAML structure argument and find the associated names and paths

        Example
        -------
        `structure: project/package/yaml` will create these variables:
            - yaml_name: the name of the base yaml file
            - yaml_path: the path to the base yaml file
            - package_name: the directory name containing the yaml file
            - package_path: the directory path containing the yaml file
            - project_name: the directory name two steps up from the yaml file
            - project_path: the directory path two steps up from the yaml file

        """
        # Input validation
        structure = self.get('structure', 'yaml')
        if not structure.endswith('yaml'):
            raise ValueError(
                '`structure` argument should end with "yaml"\n'
                f'Received: "{structure}""')
        self.variables = {'structure': structure}
        # Parse structure and find structure dirnames and abspaths
        abspath = os.path.abspath(self.path)
        filename = os.path.basename(abspath)
        paths = [('yaml', filename, abspath)]
        for var in structure.split('/')[-2::-1]:
            abspath = os.path.dirname(abspath)
            dirname = os.path.basename(abspath)
            paths.insert(0, (var, dirname, abspath))
        # Store as dict
        self.variables.update({f'{s}_name': n for s, n, _ in paths})
        self.variables.update({f'{s}_path': p for s, _, p in paths})
        # Print
        self.print('Detected structure:\n')
        self.print(tabulate(paths, headers=['SECTION', 'NAME', 'PATH']), '\n')

    def parse_variables(
        self
    ):
        """
        Load YAML variables and replace any $variables with previously
        defined variables (e.g. from the structure)

        Example
        -------
        ```
        variables:
          - script_path: $yaml_path/../script.sh
        ```
        will create a variable `script_path`, replacing $yaml_path with
        the absolute path to the yaml file

        """
        # Parse variables
        parsed = {}
        for item in self.get('variables', []):
            parsed.update(item)
        # Replace any $variables with their associated value
        for parsed_key, parsed_val in parsed.items():
            if isinstance(parsed_val, str):
                parsed_val = self._replace_variables(parsed_val)
            self.variables[parsed_key] = parsed[parsed_key] = parsed_val
        # Print
        self.print('Parsed variables:\n')
        self.pprint(parsed, sort_dicts=False)

    def _replace_variables(
        self,
        parsed_str: str,
        add_quotes: bool=False
    ):
        """
        Replace $variables with their value stored in self.variables
        If no variable is found, defaults to environment variables
        unless the --noenv flag is set

        Parameters
        ----------
        parsed_str: str
            String parsed from the yaml `variables` tag

        """
        # Find all $ or ${} variables in the string 
        quotes = '(?:"|\')'
        alphanums_in_square_brackets = \
            '(?:'                                                   + \
                '(?:\[' + quotes + '[\w_]+' + quotes + '\])'        + \
                '|'                                                 + \
                '(?:\[\$[\w_]+\])'                                  + \
                '|'                                                 + \
                '(?:\[\d+\])'                                       + \
            ')*'
        pattern = \
            '('                                                     + \
                r'\$[\w_]+' + alphanums_in_square_brackets          + \
                '|'                                                 + \
                r'\${[\w_]+' + alphanums_in_square_brackets + '}'   + \
            ')'
        parsed_variables = re.findall(pattern, parsed_str)
        var_replacements = {k: k for k in parsed_variables}
        # Find a replacement for each parsed variable
        for var in parsed_variables:
            # Split var into subkeys if var is of the form $variable['subkey']
            # E.g. "$PATHS['mypath'][$arg']" -> ["$PATHS", "mypath", "$arg"]
            regex = '\[' + '(?:\'|")*' + '(.*?)' + '(?:\'|")*' + '\]'  # ['.*']
            subkeys = re.findall(regex, var)
            subkeys.insert(0, re.findall('^\${?[\w_]+}?', var)[0])
            # Replace any $variable subkeys with the associated value
            for i, key in enumerate(subkeys):
                if key.startswith('$'):
                    key = key.strip('${}')
                    subkeys[i] = self.variables.get(key, self._environ(key))
            # If it's a collection (dict or list), iteratively get the element
            try:
                replacement = subkeys[0]
                #print(replacement)
                for k in subkeys[1:]:
                    if isinstance(replacement, list):
                        replacement = replacement[int(k)]
                    else:
                        replacement = replacement[k]
                var_replacements[var] = replacement
            except:
                pass
        # Now replace all occurences of that variable in the parsed string
        for var, replacement in var_replacements.items():
            if var == parsed_str and not add_quotes:
                parsed_str = replacement
            else:
                if isinstance(replacement, (list, dict)):
                    replacement = json.dumps(replacement, indent=4)
                    if add_quotes:
                        replacement = "'" + replacement + "'"
                else:
                    replacement = str(replacement)
                parsed_str = parsed_str.replace(var, replacement)
        return parsed_str
    
    def _environ(
        self,
        name: str
    ):
        """
        Get env variable if noenv is False

        Parameters
        ----------
        name: str
            Environment variable name

        """
        if not self.noenv:
            return os.environ.get(name, '')
        else:
            return ''

    def run_script(
        self
    ):
        """
        Parse YAML script, replace the variables and run in subprocess

        """
        script = self.get('script')
        cwd = script.get('cd', '$yaml_path')
        cwd = self._replace_variables(cwd)
        commands = script.get('run', [])
        commands = [
            self._replace_variables(cmd, add_quotes=True) for cmd in commands]
        self.print('Running script:\n')
        for cmd in commands:
            self._run_command(cmd, cwd)
    
    def _run_command(
        self,
        command_str: str,
        cwd: str
    ):
        """
        Execute a command, wait for it to finish and display the output

        Parameters
        ----------
        command_str: str
            Command to execute, as a string
        cwd: str
            Directory to run the command from

        """
        command_list = shlex.split(command_str)
        r = subprocess.run(
            command_list,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            cwd=cwd
        )
        print(r.stdout.replace('\\n', '\n'))
        if r.returncode != 0:
            raise RuntimeError(
                'Command `%s` failed.\nExit code %s: %s' % \
                (command_list, r.returncode, r.stderr))

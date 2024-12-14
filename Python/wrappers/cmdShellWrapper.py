
import subprocess
import time
from commonUtils.debugUtils import print_debug_msg as print_debug_msg
import sys
import config
from pathlib import Path
import os
import commonUtils.fileUtils as fileUtils


show_verbose = False


def delete_script_file(file_path):
    # Delete script file if exists. Returns false if could not delete
    if os.path.exists(file_path):
        os.remove(file_path)
        if os.path.exists(file_path):
            print('Could not remove properly, do NOT continue with sync')
            return False
    return True


def exec_cmd(command, wait_for_output=True, in_new_window=False):
    """
    Execute command from CMD shell (Windows) or the terminal (MacOS & Linux)
    :param command: Command to execute
    :type command: str
    :return: List of lines are returned
    :rtype: lst of str
    """

    def terminate_p_open(p_open_to_close):
        """
        Close Popen subprocess
        :param p_open_to_close: Popen to close
        :type p_open_to_close: subprocess.Popen
        """
        p_open_to_close.stderr.close()
        p_open_to_close.stdout.close()
        if p_open_to_close.stdin is not None:
            p_open_to_close.stdin.close()

    def clean_output_line(line_str):
        """
        Clean output lines so they only keep relevant information.
        """
        decoded_line = line_str.decode()
        cleaned_line = decoded_line.rstrip('\n')  # Remove n from end of line
        cleaned_line = cleaned_line.rstrip('\r')  # Remove r from end of line
        print_debug_msg(cleaned_line, show_verbose)  # Print line (if debug)
        return cleaned_line

    # If code must be executed in new cmd window
    if in_new_window:
        # If to open in new window, write commands in bat file and launch bat file.
        if sys.platform == 'win32':
            # Will need to write to file and launch that with script instead
            sync_file_path = str(Path(config.LogisticsConfig().path_logistics, 'Temp', 'sync_cmd.bat'))
            # Delete existing file at path
            result = delete_script_file(sync_file_path)
            if not result:
                return False
            # Write command to file
            command = command.replace('&', '&&')
            command = command.replace('%', '%%')
            fileUtils.write_file(sync_file_path, command)
            # Replace command by command to open previously written file
            command = 'start ' + sync_file_path
        # If to open in new window, reformat command (in macOS)
        else:
            macos_cmd_in_new_window = "osascript -e 'tell app \"Terminal\" to do script \"{}\"'"
            command = macos_cmd_in_new_window.format(command.replace('"', '\\"'))

    # Time out value (in milliseconds)
    time_out = 15

    # If debug, print command that was sent
    print_debug_msg('Initiating Execute Shell Command procedure.', show_verbose)
    print_debug_msg('Command to send:', show_verbose)
    print_debug_msg(command, show_verbose)

    # Open subprocess, until all output is received.
    p_open = subprocess.Popen(command,
                             shell=True,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             stdin=None)

    # Run loop for as long as receive new lines
    output_lines = []
    loop_begin_time = time.time()
    stdout_lst = []
    stderr_lst = []

    if wait_for_output:
        while True:
            # Status, whether it's finished shelling out results or not.
            status = p_open.poll()
            p_open.stdout.flush()

            # Standard output
            stdout = p_open.stdout.readlines()
            # Standard error
            stderr = p_open.stderr.readlines()

            if len(stdout) > 0:
                stdout_lst += stdout
            if len(stderr) > 0:
                stderr_lst += stderr

            # There is new output. Reset counter to current time.
            if stderr or stdout:
                loop_begin_time = time.time()

            # If finished
            if status is not None:  # When status is not None, has finished sending results.
                output_lines = stdout_lst + stderr_lst
                terminate_p_open(p_open)  # Terminate open process
                break

            # If took too long, break off from the while loop
            now = time.time()
            if now - loop_begin_time > time_out:
                terminate_p_open(p_open)
                break

    # If debug, print result
    print_debug_msg('Output lines:', show_verbose)

    # Clean the output lines
    output_lines_cleaned = []
    for line in output_lines:
        output_lines_cleaned.append(clean_output_line(line))  # Append clean line to result

    # Return result
    return output_lines_cleaned

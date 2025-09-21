# Logistics

Logistics is a collection of tools I created to streamline my computer interactions. Its core functionality revolves around **rclone integration**, enabling easy remote management and data transfer between my computers and cloud storage. Beyond rclone, Logistics offers convenient access to frequently used websites, smart home control, and automated tasks.

## Features

*   **Useful Website Links Tab**
    *   Quick access to commonly used webpages and media libraries (comic books, movies, etc.).
*   **Smart Home Tab**
    *   Control lights and other smart home devices.
*   **Rclone Integration (Local + Remote)**
    *   Easily add remotes to any computer.
    *   Perform push/pull operations from/to the remote storage.
*   **Useful Codes and Automated Tasks Tab**
    *   Set the Mac to not sleep when the lid is closed.
    *   Compress each file in a directory into a zip archive.

## Installation and Usage

To use Logistics, you will need to pull it from my existing rclone remote (rather than get it from GitHUB).  The repository includes two additional folders necessary for the tool to function properly: `📂RemoteCredentials` and `📂Software`.

1.  **Pull from Rclone Remote:** Pull the Logistics remote using your preferred method, or simply copy it from another computer. Have it located at Server/Logistics in the current user's home directory (for example `📂/Users/marca/Server/Logistics`).
2.  **Install Dependencies:** Mandatory: Install the required dependency (macOS: `macfuse`, Windows: `winfsp`) located in the `📂Software` subdirectory. Optional: Other install additional software in there.
3.  **Launch:** Launch the tool by double-clicking the launch file (macOS: `📄LaunchLogistics_MAC.COMMAND`, Windows: `📄LaunchLogistics_MAC.BAT`) 
4.  **Load Remote Credential:** Load rclone remote(s) using the `Load Remote Credentials` button on the bottom-left of the UI.
5.  **Run:** Run whichever tool you need.

## Repository Structure

*   `📂Python`: The main Logistics application code.
*   `📂RemoteCredentials`: Configuration files for rclone remotes.  **Important: Handle these credentials securely!**
*   `📂Scripts`: One-off scripts.
*   `📂Software`: Any necessary software or scripts required by Logistics in some way(s).

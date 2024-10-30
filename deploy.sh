#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Function to print status messages
print_status() {
    echo -e "${GREEN}[*] $1${NC}"
}

# Function to print error messages
print_error() {
    echo -e "${RED}[!] $1${NC}"
}

# Function to check if command succeeded
check_status() {
    if [ $? -eq 0 ]; then
        print_status "$1 successful"
    else
        print_error "$1 failed"
        exit 1
    fi
}

# Function to install system dependencies
install_system_deps() {
    print_status "Installing system dependencies..."
    
    # Update system
    sudo apt -y update
    sudo apt -y upgrade
    check_status "System update"

    # Install required system packages
    sudo apt install -y \
        git \
        build-essential \
        libgl1-mesa-glx \
        libglib2.0-0 \
        wget \
        curl \
        openssh-server
    check_status "System packages installation"
}

# Function to install Python 3.11
install_python() {
    print_status "Installing Python 3.11..."
    
    sudo add-apt-repository -y ppa:deadsnakes/ppa
    sudo apt -y update
    
    sudo apt install -y \
        python3.11 \
        python3.11-venv \
        python3.11-distutils \
        python3.11-dev
    check_status "Python 3.11 installation"
}

# Function to setup SSH
setup_ssh() {
    print_status "Setting up SSH..."
    
    sudo systemctl enable ssh
    sudo systemctl start ssh
    
    # Configure firewall
    sudo ufw allow ssh
    sudo ufw --force enable
    check_status "SSH setup"
}

# Function to setup the project
setup_project() {
    print_status "Setting up project..."
    
    # Clone repository
    git clone https://github.com/fahnub/pickleball-events.git
    check_status "Repository clone"
    
    cd pickleball-events
    
    # Create and activate virtual environment
    python3.11 -m venv venv
    source venv/bin/activate
    check_status "Virtual environment setup"
    
    # Install Python dependencies
    pip install --upgrade pip
    pip install -r requirements.txt
    check_status "Python dependencies installation"
}

# Function to create systemd service
create_service() {
    print_status "Creating systemd service..."
    
    # Create service file for the web server
    sudo tee /etc/systemd/system/pickleball-server.service << EOF
[Unit]
Description=Pickleball Events Web Server
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
Environment="PATH=$(pwd)/venv/bin"
ExecStart=$(pwd)/venv/bin/python server.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    # Create service file for the main application
    sudo tee /etc/systemd/system/pickleball-main.service << EOF
[Unit]
Description=Pickleball Events Main Application
After=pickleball-server.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
Environment="PATH=$(pwd)/venv/bin"
Environment="DISPLAY=:0"
ExecStart=$(pwd)/venv/bin/python run.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    # Enable and start services
    sudo systemctl daemon-reload
    sudo systemctl enable pickleball-server.service
    sudo systemctl enable pickleball-main.service
    sudo systemctl start pickleball-server.service
    sudo systemctl start pickleball-main.service
    
    check_status "Service creation"
}

# Function to verify installation
verify_installation() {
    print_status "Verifying installation..."
    
    # Check Python version
    python3.11 --version
    check_status "Python version check"
    
    # Check if services are running
    sudo systemctl status pickleball-server.service
    sudo systemctl status pickleball-main.service
    check_status "Service status check"
    
    # Check if web server is responding
    curl -s http://localhost:5000 > /dev/null
    check_status "Web server check"
}

# Main installation process
main() {
    print_status "Starting installation..."
    
    install_system_deps
    install_python
    setup_ssh
    setup_project
    create_service
    verify_installation
    
    print_status "Installation complete! Services are running."
    print_status "Web interface available at: http://localhost:5000"
    print_status "SSH access enabled"
}

# Run main function
main

# Exit successfully
exit 0 
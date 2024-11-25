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
        v4l-utils \
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

# Function to cleanup existing installation
cleanup_existing() {
    print_status "Cleaning up existing installation..."
    
    if [ -d "pickleball-events" ]; then
        rm -rf pickleball-events
    fi
    check_status "Cleanup"
}

# Function to install Python dependencies with retry
install_python_deps() {
    local max_attempts=3
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        print_status "Installing Python dependencies (Attempt $attempt of $max_attempts)..."
        
        # Increase timeout and retries for pip
        pip install --upgrade pip
        pip install --timeout 120 --retries 3 -r requirements.txt
        
        if [ $? -eq 0 ]; then
            print_status "Python dependencies installation successful"
            return 0
        fi
        
        print_error "Attempt $attempt failed. Retrying..."
        attempt=$((attempt + 1))
        sleep 5
    done
    
    print_error "Failed to install Python dependencies after $max_attempts attempts"
    return 1
}

# Function to setup the project
setup_project() {
    print_status "Setting up project..."
    
    cleanup_existing
    
    # Clone repository
    git clone https://github.com/fahnub/pickleball-events.git
    check_status "Repository clone"
    
    cd pickleball-events
    
    # Create and activate virtual environment
    python3.11 -m venv venv
    source venv/bin/activate
    check_status "Virtual environment setup"
    
    # Install Python dependencies with retry logic
    install_python_deps
    check_status "Python dependencies installation"
}

# Function to create systemd service
create_service() {
    print_status "Creating systemd service..."

    # Create service file for main application
    sudo tee /etc/systemd/system/pickleball-main.service << EOF
[Unit]
Description=Pickleball Events Main Application
After=network.target

[Service]
Type=simple
User=$USER
SupplementaryGroups=video
WorkingDirectory=$(pwd)
Environment="PATH=$(pwd)/venv/bin"
Environment="DISPLAY=:0"
Environment=XDG_RUNTIME_DIR=/run/user/1000
ExecStart=$(pwd)/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    # Enable and start services
    sudo ufw allow 8080
    sudo systemctl daemon-reload
    sudo systemctl enable pickleball-main.service
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
    sudo systemctl status pickleball-main.service
    check_status "Service status check"
    
    # Check if web server is responding
    curl -s http://localhost:8080 > /dev/null
    check_status "Web server check"
}

# Function to install and configure Samba
setup_samba() {
    print_status "Setting up Samba..."
    
    # Install Samba
    sudo apt install -y samba
    check_status "Samba installation"
    
    # Backup original config
    sudo cp /etc/samba/smb.conf /etc/samba/smb.conf.backup
    
    # Create new Samba configuration
    sudo tee /etc/samba/smb.conf << EOF
[global]
   workgroup = WORKGROUP
   server string = Pickleball Vision
   security = user
   map to guest = bad user
   dns proxy = no

[root]
   path = /
   browseable = yes
   writable = yes
   guest ok = no
   read only = no
   create mask = 0755
   directory mask = 0755
   force user = root
EOF
    
    # Set Samba password for current user
    print_status "Setting up Samba user password..."
    sudo smbpasswd -a $USER
    
    # Restart Samba service
    sudo systemctl restart smbd
    sudo systemctl restart nmbd
    
    # Configure firewall for Samba
    sudo ufw allow samba
    
    check_status "Samba configuration"
}

# Main installation process
main() {
    print_status "Starting installation..."
    
    install_system_deps
    install_python
    setup_ssh
    setup_samba
    setup_project
    create_service
    verify_installation
    
    print_status "Installation complete! Services are running."
    print_status "Web interface available at: http://localhost:5000"
    print_status "SSH access enabled"
    print_status "Samba share available at: \\\\$(hostname)\\root"
    print_status "Use your Ubuntu username and Samba password to connect"
}

# Run main function
main

# Exit successfully
exit 0 
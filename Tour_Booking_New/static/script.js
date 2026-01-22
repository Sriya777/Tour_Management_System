// Real-time updates and interactive features
document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl)
    });

    // Real-time form validation
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const requiredFields = form.querySelectorAll('[required]');
            let valid = true;

            requiredFields.forEach(field => {
                if (!field.value.trim()) {
                    valid = false;
                    field.classList.add('is-invalid');
                } else {
                    field.classList.remove('is-invalid');
                }
            });

            if (!valid) {
                e.preventDefault();
                showAlert('Please fill in all required fields.', 'danger');
            }
        });
    });

    // Password strength indicator
    const passwordInput = document.getElementById('password');
    if (passwordInput) {
        passwordInput.addEventListener('input', function() {
            const strengthIndicator = document.getElementById('password-strength');
            if (strengthIndicator) {
                const strength = calculatePasswordStrength(this.value);
                strengthIndicator.textContent = strength.text;
                strengthIndicator.className = `badge bg-${strength.color}`;
            }
        });
    }

    // Real-time search for packages
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        let searchTimeout;
        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                this.form.submit();
            }, 500);
        });
    }

    // Rating system for feedback
    const ratingStars = document.querySelectorAll('.rating-star');
    ratingStars.forEach(star => {
        star.addEventListener('click', function() {
            const rating = this.getAttribute('data-rating');
            const hiddenInput = document.getElementById('rating');
            if (hiddenInput) {
                hiddenInput.value = rating;
            }
            
            // Update star display
            ratingStars.forEach(s => {
                if (s.getAttribute('data-rating') <= rating) {
                    s.classList.add('text-warning');
                    s.classList.remove('text-muted');
                } else {
                    s.classList.remove('text-warning');
                    s.classList.add('text-muted');
                }
            });
        });
    });

    // Auto-update total amount when travelers count changes
    const travelersCountInput = document.getElementById('travelers_count');
    const priceDisplay = document.getElementById('package_price');
    const totalAmountDisplay = document.getElementById('total_amount');
    
    if (travelersCountInput && priceDisplay && totalAmountDisplay) {
        travelersCountInput.addEventListener('input', function() {
            const price = parseFloat(priceDisplay.textContent);
            const count = parseInt(this.value) || 0;
            const total = price * count;
            totalAmountDisplay.textContent = total.toFixed(2);
        });
    }

    // Real-time notification system
    function showAlert(message, type = 'info') {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        const container = document.querySelector('.container');
        container.insertBefore(alertDiv, container.firstChild);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.remove();
            }
        }, 5000);
    }

    // Package availability check
    function checkPackageAvailability(packageId) {
        fetch(`/api/package/${packageId}/availability`)
            .then(response => response.json())
            .then(data => {
                if (data.available_slots === 0) {
                    const bookBtn = document.querySelector('.book-btn');
                    if (bookBtn) {
                        bookBtn.disabled = true;
                        bookBtn.textContent = 'Fully Booked';
                    }
                }
            })
            .catch(error => console.error('Error checking availability:', error));
    }

    // Smooth scrolling for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });

    // Dynamic content loading
    function loadMoreContent(url, container) {
        fetch(url)
            .then(response => response.text())
            .then(html => {
                container.innerHTML += html;
            })
            .catch(error => console.error('Error loading content:', error));
    }

    // Initialize any package availability checks
    const packageId = document.getElementById('package_id');
    if (packageId) {
        checkPackageAvailability(packageId.value);
    }
});

// Password strength calculator
function calculatePasswordStrength(password) {
    let strength = 0;
    
    if (password.length >= 6) strength++;
    if (password.length >= 8) strength++;
    if (/[A-Z]/.test(password)) strength++;
    if (/[0-9]/.test(password)) strength++;
    if (/[^A-Za-z0-9]/.test(password)) strength++;
    
    switch(strength) {
        case 0:
        case 1:
        case 2:
            return { text: 'Weak', color: 'danger' };
        case 3:
        case 4:
            return { text: 'Medium', color: 'warning' };
        case 5:
            return { text: 'Strong', color: 'success' };
        default:
            return { text: 'Weak', color: 'danger' };
    }
}

// API functions for real-time updates
const TourBookAPI = {
    // Check package availability
    checkAvailability: async function(packageId) {
        try {
            const response = await fetch(`/api/package/${packageId}/availability`);
            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            return { available_slots: 0 };
        }
    },

    // Get user recommendations
    getRecommendations: async function(userId) {
        try {
            const response = await fetch(`/api/user/${userId}/recommendations`);
            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            return [];
        }
    },

    // Submit feedback
    submitFeedback: async function(feedbackData) {
        try {
            const response = await fetch('/api/feedback', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(feedbackData)
            });
            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            return { success: false, message: 'Failed to submit feedback' };
        }
    }
};

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { TourBookAPI, calculatePasswordStrength };
}

// Add real-time notification system
function showNotification(message, type = 'info') {
    // Create and show toast notification
}
document.addEventListener("DOMContentLoaded", function () {

    const csrfToken = document.querySelector('meta[name="csrf-token"]').content;

    // --- Get the notifications URL from the script tag in base.html --//
    const mainScript = document.getElementById('main-js');
    const NOTIFICATIONS_URL = mainScript.dataset.notificationsUrl;

    // --- Socket.IO and Notifications ---
    window.socket = io.connect(window.location.protocol + "//" + document.domain + ":" + location.port);
    const notificationSound = new Audio("/static/sounds/notify.wav");

    socket.on("connect", () => {});

    socket.on("new_notification", (data) => {
        try {
            // Check if we are on the notifications page ---
            if (!document.getElementById('notifications-page-wrapper')) {
                const bell = document.getElementById("notification-count");
                if (bell) {
                    const currentCount = parseInt(bell.innerText || "0");
                    bell.innerText = currentCount + 1;
                    bell.style.display = 'block';
                }
            } else {
                prependNotificationToList(data);
            }
            
            // --- ALWAYS show the new flash toast ---
            showFlashToast(data.message, timeAgo(data.created_at), data.url);
    
            // Play sound
            if (document.visibilityState === "visible") {
                notificationSound.play().catch(e => {});
            }
        } catch (error) {
            // Silent error handling
        }
    });

    // --- All Helper Functions ---
    function showFlashToast(message, time, url) {
        const container = document.getElementById('toast-container');
        if (!container) return;
        const toast = document.createElement("a");
        toast.href = url || '#';
        toast.className = "toast-flash";
        toast.innerHTML = `
            <div class="toast-message">${message}</div>
            <div class="toast-time">${time}</div>
        `;
        container.appendChild(toast);
        setTimeout(() => toast.classList.add('show'), 100);
        setTimeout(() => {
            toast.classList.remove('show');
            toast.addEventListener('transitionend', () => toast.remove());
        }, 10000);
    }

    function timeAgo(dateString) {
        const date = new Date(dateString);
        const now = new Date();
        const seconds = Math.round((now - date) / 1000);
        const minutes = Math.round(seconds / 60);
        const hours = Math.round(minutes / 60);
        if (seconds < 60) return `just now`;
        if (minutes < 60) return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
        if (hours < 24) return `${hours} hour${hours > 1 ? 's' : ''} ago`;
        return new Date(dateString).toLocaleDateString("en-US", { month: 'short', day: 'numeric' });
    }

    function prependNotificationToList(notif) {
        const listContainer = document.querySelector('.notification-list');
        if (!listContainer) return;
        const newNotifRow = document.createElement('div');
        newNotifRow.className = 'notification-row unread-notification';
        newNotifRow.innerHTML = `
            <div class="notification-icon"><div class="icon-circle"><i class="fas fa-user"></i></div></div>
            <div class="notification-body"><p class="notification-message mb-1">${notif.message}</p><small class="notification-timestamp text-muted">${timeAgo(notif.created_at)}</small></div>
            <div class="notification-actions"><a href="${notif.url || '#'}" class="btn btn-sm btn-outline-primary action-btn">View</a><small class="notification-date text-muted">${new Date(notif.created_at).toLocaleDateString("en-US", { month: 'long', day: 'numeric', year: 'numeric' })}</small></div>
        `;
        listContainer.prepend(newNotifRow);
    }

    // --- Initial notification count loader function ---
    async function loadInitialNotificationCount() {
        if (document.getElementById('notifications-page-wrapper')) {
            return;
        }
        try {
            // ✅ FIXED: Use the URL passed in from base.html
            const response = await fetch(NOTIFICATIONS_URL);
            const unread_notifications = await response.json();
            const count = unread_notifications.length;
            const bell = document.getElementById("notification-count");
            if (bell) {
                if (count > 0) {
                    bell.innerText = count;
                    bell.style.display = 'block';
                } else {
                    bell.style.display = 'none';
                }
            }
        } catch (error) {
            // Silent error handling
        }
    }

    // --- Auto-hide flashed alerts ---
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(function (alert) {
        setTimeout(function () {
            alert.classList.remove('show');
            alert.classList.add('hide');
            setTimeout(() => alert.remove(), 500);
        }, 45000);
    });

    // --- Initialize everything that needs to run on page load ---
    loadInitialNotificationCount();

    // --- Autocomplete for Client Input ---
    const clientInput = document.getElementById('client');
    const clientIdHidden = document.getElementById('client_id');
    const suggestionsContainer = document.getElementById('client-suggestions');

    if (clientInput && clientIdHidden && suggestionsContainer) {
        let typingTimer;
        const doneTypingInterval = 300;

        clientInput.addEventListener('input', function() {
            clearTimeout(typingTimer);
            clientIdHidden.value = ''; // Clear hidden client_id
            const query = this.value;

            if (query.length < 2) {
                suggestionsContainer.style.display = 'none';
                suggestionsContainer.innerHTML = '';
                return;
            }

            typingTimer = setTimeout(() => fetchClientSuggestions(query), doneTypingInterval);
        });

        function fetchClientSuggestions(query) {
            fetch(`/clients/search?q=${encodeURIComponent(query)}`)
                .then(response => response.json())
                .then(data => {
                    const clients = data.clients;
                    let suggestionHtml = '';
                    if (clients && clients.length > 0) {
                        clients.forEach(client => {
                            suggestionHtml += `<a href="#" class="list-group-item list-group-item-action" data-id="${client.id}" data-name="${client.name}">${client.name}</a>`;
                        });
                    } else {
                        suggestionHtml = '<div class="list-group-item text-muted">No clients found</div>';
                    }
                    suggestionsContainer.innerHTML = suggestionHtml;
                    suggestionsContainer.style.display = 'block';
                })
                .catch(error => {});
        }

        suggestionsContainer.addEventListener('click', function(e) {
            if (e.target.tagName === 'A') {
                e.preventDefault();
                const name = e.target.dataset.name;
                const id = e.target.dataset.id;
                clientInput.value = name;
                clientIdHidden.value = id;
                this.style.display = 'none';
                this.innerHTML = '';
            }
        });

        document.addEventListener('click', function(event) {
            if (!clientInput.contains(event.target) && !suggestionsContainer.contains(event.target)) {
                suggestionsContainer.style.display = 'none';
            }
        });
    }

    // --- Dynamic Task Template Dropdown ---
    const taskTemplateSelect = document.getElementById('task_template_id');
    if (taskTemplateSelect) {
        taskTemplateSelect.addEventListener('change', function () {
            const selectedOption = this.options[this.selectedIndex];
            const title = selectedOption.getAttribute('data-title');
            const description = selectedOption.getAttribute('data-description');
            document.getElementById('title').value = title || '';
            document.getElementById('description').value = description || '';
        });
    }

    // --- Service and Template Filtering ---
    const serviceSelect = document.getElementById('service_id');
    if (serviceSelect && taskTemplateSelect) {
        serviceSelect.addEventListener('change', function () {
            const selectedServiceId = this.value;
            Array.from(taskTemplateSelect.options).forEach(option => {
                const templateServiceId = option.getAttribute('data-service-id');
                if (!templateServiceId || selectedServiceId === "") {
                    option.style.display = 'none';
                } else {
                    option.style.display = (templateServiceId === selectedServiceId) ? 'block' : 'none';
                }
            });
            taskTemplateSelect.value = "";
            document.getElementById('title').value = "";
            document.getElementById('description').value = "";
        });
    }

    // --- Set Default Datetime ---
    const deadlineInput = document.getElementById('deadline');
    if (deadlineInput) {
        const now = new Date();
        now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
        deadlineInput.value = now.toISOString().slice(0,16);
    }

    // --vat form saving and shoing modal functions ---

    const vatFormModal = document.getElementById('vatFormModal');
    const vatFormContent = document.getElementById('vatFormModalContent');
    let autoSaveIntervalId = null;

    if (!vatFormModal || !vatFormContent) return;

    // This function re-fetches the form HTML from the server and replaces the old content.
    // It's the key to making the form feel real-time.
    async function refreshFormContent(viewUrl) {
        if (!viewUrl) return;
        
        const oldContainer = document.getElementById('vatReportContainer');
        if (!oldContainer) return;

        // 1. Remember the URLs and edit mode state from the OLD container
        const saveUrl = oldContainer.getAttribute('data-save-url');
        const wasInEditMode = oldContainer.classList.contains('edit-mode-active');
        
        try {
            const response = await fetch(viewUrl);
            if (!response.ok) throw new Error('Failed to reload form content.');
            const html = await response.text();
            vatFormContent.innerHTML = html;

            // 2. Find the NEW container and re-apply the attributes
            const newContainer = document.getElementById('vatReportContainer');
            if (newContainer) {
                newContainer.setAttribute('data-view-url', viewUrl);
                newContainer.setAttribute('data-save-url', saveUrl);

                // 3. Restore edit mode if it was active
                if (wasInEditMode) {
                    toggleEditMode(newContainer, true);
                }

                setupVatFormCalculations(newContainer);
                initTaxLiabilityEvents(newContainer);

                // bismillah 

            }
        } catch (error) {
            // Silent error handling
        }
    }
    
    // --- 1. SETUP WHEN MODAL IS SHOWN ---
    vatFormModal.addEventListener('show.bs.modal', function (event) {
        if (autoSaveIntervalId) clearInterval(autoSaveIntervalId);

        const button = event.relatedTarget;
        const viewUrl = button.getAttribute('data-vat-url');
        const saveUrl = button.getAttribute('data-vat-save-url');
        
        vatFormContent.innerHTML = `<div class="text-center py-5"><div class="spinner-border text-primary" role="status"></div></div>`;
        
        fetch(viewUrl)
            .then(response => response.ok ? response.text() : Promise.reject('Failed to load form.'))
            .then(html => {
                vatFormContent.innerHTML = html;
                const container = document.getElementById('vatReportContainer');
                if(container) {
                    container.setAttribute('data-view-url', viewUrl);
                    container.setAttribute('data-save-url', saveUrl);
                    initTaxLiabilityEvents(container);
                }
            })
            .catch(err => {
                 vatFormContent.innerHTML = `<div class="alert alert-danger">${err}</div>`;
            });
    });

    // --- 2. HANDLE BUTTON CLICKS (EDIT, CANCEL, SAVE) ---
    vatFormContent.addEventListener('click', async function(event) {
        const container = document.getElementById('vatReportContainer');
        if (!container) return;

        const editBtn = event.target.closest('#editVatFormBtn');
        const cancelBtn = event.target.closest('#cancelEditBtn');
        const saveBtn = event.target.closest('#manualSaveBtn');

        //bismilah 
        const toggleBtn = event.target.closest('#toggleVatViewBtn');


        if (editBtn) {
            // Check if we are currently in edit mode (i.e., button is set to 'View Mode')
            if (container.classList.contains('edit-mode-active')) {
                // Sequence to go to View Mode: Save -> Refresh -> Exit Edit Mode
                await performSave(container); 
                await refreshFormContent(container.getAttribute('data-view-url')); 
                toggleEditMode(container, false); // **Explicitly switch to View Mode**
            } else {
                // Sequence to go to Edit Mode
                toggleEditMode(container, true); 
            }
        } else if (cancelBtn) {
            stopAutoSave();
            // Sequence to cancel: Refresh -> Exit Edit Mode
            await refreshFormContent(container.getAttribute('data-view-url'));
            toggleEditMode(container, false); 
        } else if (saveBtn) {
            // Sequence for manual save: Save -> Refresh -> Exit Edit Mode
            await performSave(container); 
            await refreshFormContent(container.getAttribute('data-view-url'));
            toggleEditMode(container, false); 
        } 

        if (toggleBtn) {
            const vatTable = document.getElementById('prevVatSummaryTable');
            if (vatTable) {
                vatTable.classList.toggle('simple-view');
                const isSimpleView = vatTable.classList.contains('simple-view');
                
                // Update button text
                if (isSimpleView) {
                    toggleBtn.innerHTML = '<i class="fas fa-expand-alt me-1"></i> Show Detailed View';
                } else {
                    toggleBtn.innerHTML = '<i class="fas fa-compress-alt me-1"></i> Show Simple View';
                }
            }
        }




    });
    
    // --- EDIT MODE TOGGLE ---

    function toggleEditMode(container, forceEdit) {
        if(!container) return;
    
        const buttonToUpdate = document.getElementById('editVatFormBtn');
        
        if (forceEdit) {
            // ENTER EDIT MODE
            container.classList.add('edit-mode-active');
            if (buttonToUpdate) buttonToUpdate.innerHTML = '<i class="fas fa-eye me-1"></i> View Mode';
            startAutoSave(container);
        } else {
            // EXIT EDIT MODE (GO TO VIEW MODE)
            container.classList.remove('edit-mode-active');
            if (buttonToUpdate) buttonToUpdate.innerHTML = '<i class="fas fa-edit me-1"></i> Edit';
            stopAutoSave();
        }
    }

    // --- 3. DATA COLLECTION AND SAVING LOGIC ---
    function getVatFormData() {
        const data = {};
        const fields = vatFormContent.querySelectorAll('#vatReportContainer [name]');
        
        fields.forEach(field => {
            if (field.type === 'checkbox') {
                data[field.name] = field.checked;
            } else if (field.type === 'radio') {
                if(field.checked) data[field.name] = field.value;
            } else {
                data[field.name] = field.value;
            }
        });
        return data;
    }

    async function performSave(container) {
        const formData = getVatFormData();
        const saveUrl = container.getAttribute('data-save-url');
        const saveBtn = document.getElementById('manualSaveBtn');
        
        if (!saveUrl) {
            return;
        }


        //bismillah- remove later
        // DEBUG: Log historical VAT data
        console.log("=== Historical VAT Data Being Sent ===");
        const historicalFields = {};
        Object.keys(formData).forEach(key => {
            // Look for fields like sales_zero_rated_JAN, output_vat_16_FEB, etc.
            if (key.includes('sales_') || key.includes('purchases_') || 
                key.includes('output_') || key.includes('input_') ||
                key.includes('withheld_') || key.includes('balance_') ||
                key.includes('paid_')) {
                historicalFields[key] = formData[key];
            }
        });
        console.log("Historical VAT fields:", historicalFields);
        console.log("Total historical fields found:", Object.keys(historicalFields).length);
        console.log("=== End Debug ===");





        //bismillah- remove later

            const taxLiabilityFields = {};
        Object.keys(formData).forEach(key => {
            if (key.includes('tl_')) {
                taxLiabilityFields[key] = formData[key];
            }
        });
        console.log("Tax Liability Fields:", taxLiabilityFields);

            // Show delete checkboxes specifically
            const deleteFields = {};
            Object.keys(formData).forEach(key => {
                if (key.includes('tl_delete_')) {
                    deleteFields[key] = formData[key];
                }
            });
            console.log("Delete Checkboxes:", deleteFields);
            console.log("=== End Debug ===");

        // end of bismillah- remove later

        if (saveBtn) {
            saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Saving...';
            saveBtn.disabled = true;
        }

        try {
            const response = await fetch(saveUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json',
                'X-CSRFToken':csrfToken
                 },
                body: JSON.stringify(formData)

            });

            const result = await response.json();
            if (!response.ok) throw new Error(result.message || 'Save failed on server.');
            
        } catch (error) {
            // Silent error handling
        } finally {
            if (saveBtn) {
                saveBtn.innerHTML = '<i class="fas fa-save me-1"></i> Save Now';
                saveBtn.disabled = false;
            }
        }
    }

    function setupVatFormCalculations(container) {
        if (!container) return;
        
        // Remove any existing event listeners
        container.removeEventListener('input', updateCalculations);
        
        // Add new event listener
        container.addEventListener('input', updateCalculations);
        updateCalculations();
    }

    function updateCalculations() {
        const container = document.getElementById('vatReportContainer');
        if (!container) return;
        
        const getVal = (name) => parseFloat(container.querySelector(`[name="${name}"]`)?.value) || 0;
        const setVal = (name, value) => {
            const input = container.querySelector(`input[name="${name}"]`);
            if (input) input.value = value.toFixed(2);
        };
        
        const regVatable16 = getVal('reg_customers_vatable_16');
        const regVatable8 = getVal('reg_customers_vatable_8');
        const regZero = getVal('reg_customers_zero_rated');
        const regExempt = getVal('reg_customers_exempt');
        const nonRegVatable16 = getVal('non_reg_customers_vatable_16');
        const nonRegVatable8 = getVal('non_reg_customers_vatable_8');
        const nonRegZero = getVal('non_reg_customers_zero_rated');
        const nonRegExempt = getVal('non_reg_customers_exempt');
        const purchVatable16 = getVal('purchases_vatable_16');
        const purchVatable8 = getVal('purchases_vatable_8');
        const purchZero = getVal('purchases_zero_rated');
        const purchExempt = getVal('purchases_exempt');
        const vatWhCredit = getVal('vat_wh_credit');
        const creditBf = getVal('credit_bf');
        
        const regVat = (regVatable16 * 0.16) + (regVatable8 * 0.08);
        const nonRegVat = (nonRegVatable16 * 0.16) + (nonRegVatable8 * 0.08);
        const purchVat = (purchVatable16 * 0.16) + (purchVatable8 * 0.08);
        const regTotal = regVatable16 + regVatable8 + regZero + regExempt;
        const nonRegTotal = nonRegVatable16 + nonRegVatable8 + nonRegZero + nonRegExempt;
        const purchTotal = purchVatable16 + purchVatable8 + purchZero + purchExempt;
        const totalSalesVat = regVat + nonRegVat;
        const totalSalesZero = regZero + nonRegZero;
        const totalSalesExempt = regExempt + nonRegExempt;
        const totalSalesTotal = regTotal + nonRegTotal;
        const vatPayable = totalSalesVat - purchVat - vatWhCredit - creditBf;
        
        setVal('reg_customers_vat', regVat);
        setVal('reg_customers_total', regTotal);
        setVal('non_reg_customers_vat', nonRegVat);
        setVal('non_reg_customers_total', nonRegTotal);
        setVal('purchases_vat', purchVat);
        setVal('purchases_total', purchTotal);
        setVal('total_sales_vat_display', totalSalesVat);
        setVal('total_sales_zero_rated_display', totalSalesZero);
        setVal('total_sales_exempt_display', totalSalesExempt);
        setVal('total_sales_total_display', totalSalesTotal);
        setVal('vat_payable_display', vatPayable);
    }

    // Update recycle bin count
    function updateRecycleBinCount() {
        fetch('/recycle-bin/stats')
            .then(response => response.json())
            .then(data => {
                const count = data.count || 0;
                const badge = document.getElementById('recycle-bin-count');
                const statElement = document.getElementById('recycle-bin-stat');
                
                if (badge) {
                    if (count > 0) {
                        badge.textContent = count;
                        badge.style.display = 'block';
                    } else {
                        badge.style.display = 'none';
                    }
                }
                
                if (statElement) {
                    statElement.textContent = count + ' Item' + (count !== 1 ? 's' : '');
                }
            })
            .catch(error => {});
    }

    // --- RECYCLE BIN COUNT ---
    function updateRecycleBinCount() {
        fetch('/recycle-bin/stats')
            .then(response => response.json())
            .then(data => {
                const count = data.count || 0;
                const badge = document.getElementById('recycle-bin-count');
                const statElement = document.getElementById('recycle-bin-stat');
                
                if (badge) {
                    if (count > 0) {
                        badge.textContent = count;
                        badge.style.display = 'block';
                    } else {
                        badge.style.display = 'none';
                    }
                }
                
                if (statElement) {
                    statElement.textContent = count + ' Item' + (count !== 1 ? 's' : '');
                }
            })
            .catch(error => console.error('Error updating recycle bin count:', error));
    }

    // Add this function to highlight rows marked for deletion
    function initTaxLiabilityEvents(container) {
        if (!container) return;
        
        // Highlight rows when delete checkbox is checked
        container.addEventListener('change', function(event) {
            const checkbox = event.target;
            if (checkbox.classList.contains('delete-checkbox')) {
                const row = checkbox.closest('tr');
                if (checkbox.checked) {
                    row.classList.add('table-danger');
                    row.style.opacity = '0.6';
                } else {
                    row.classList.remove('table-danger');
                    row.style.opacity = '1';
                }
            }
        });
        
        // Handle "Add New Row" button click
        const addRowBtn = container.querySelector('#addTaxLiabilityRow');
        if (addRowBtn) {
            addRowBtn.addEventListener('click', function() {
                const tbody = container.querySelector('#taxLiabilityTbody');
                if (!tbody) return;
                
                // Create a new row
                const newRow = document.createElement('tr');
                newRow.className = 'edit-mode-element new-dynamic-row';
                newRow.innerHTML = `
                    <td><input type="text" class="form-control form-control-sm" name="new_tl_period[]" placeholder="Period"></td>
                    <td><input type="text" class="form-control form-control-sm" name="new_tl_tax_head[]" placeholder="Tax Head"></td>
                    <td><input type="number" step="0.01" class="form-control form-control-sm" name="new_tl_principal[]" placeholder="Principal"></td>
                    <td><input type="number" step="0.01" class="form-control form-control-sm" name="new_tl_penalty[]" placeholder="Penalty"></td>
                    <td><input type="number" step="0.01" class="form-control form-control-sm" name="new_tl_interest[]" placeholder="Interest"></td>
                    <td><input type="number" step="0.01" class="form-control form-control-sm" name="new_tl_total[]" placeholder="Total"></td>
                    <td class="text-center">
                        <button type="button" class="btn btn-sm btn-outline-danger remove-dynamic-row">
                            <i class="fas fa-times"></i>
                        </button>
                    </td>
                `;
                
                // Insert before the existing new-entry row
                const existingNewEntryRow = tbody.querySelector('.new-entry-row');
                if (existingNewEntryRow) {
                    tbody.insertBefore(newRow, existingNewEntryRow);
                } else {
                    tbody.appendChild(newRow);
                }
            });
        }
        
        // Handle removing dynamically added rows
        container.addEventListener('click', function(event) {
            const removeBtn = event.target.closest('.remove-dynamic-row');
            if (removeBtn) {
                const row = removeBtn.closest('tr');
                if (row && row.classList.contains('new-dynamic-row')) {
                    row.remove();
                }
            }
        });
    }

    // Initialize recycle bin count
    updateRecycleBinCount();
    
    // Update every 2 minutes
    setInterval(updateRecycleBinCount, 120000);


    // Add this function to handle adding new tax liability rows



});
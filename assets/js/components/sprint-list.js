export default function sprintList() {
  return {
    selectedCount: 0,
    showBulkDeleteModal: false,
    showBulkOwnerModal: false,
    ownerConfirmStep: false,
    selectedOwnerName: '',
    selectedOwnerValue: '',
    showFiltersModal: false,
    showNewSprintModal: false,

    init() {
      this.$watch('showBulkOwnerModal', (open) => {
        if (!open) return;
        this.ownerConfirmStep = false;
        this.selectedOwnerName = 'Unassigned';
        this.selectedOwnerValue = '';
        const none = document.getElementById('owner-none');
        if (none) none.checked = true;
      });
    },
  };
}

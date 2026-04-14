export default function projectList() {
  return {
    selectedCount: 0,
    showBulkDeleteModal: false,
    showBulkLeadModal: false,
    showBulkMoveModal: false,
    showCascadeModal: false,
    leadConfirmStep: false,
    selectedLeadName: '',
    selectedLeadValue: '',
    moveConfirmStep: false,
    selectedMoveWorkspaceName: '',
    selectedMoveWorkspaceValue: '',
    showFiltersModal: false,
    showNewProjectModal: false,

    confirmBulkMove() {
      document.querySelectorAll('[name=projects]:checked').forEach(cb => cb.closest('tr').remove());
      const sa = document.getElementById('select-all');
      if (sa) sa.checked = false;
      this.selectedCount = 0;
      this.showBulkMoveModal = false;
      this.moveConfirmStep = false;
    },

    init() {
      this.$watch('showBulkLeadModal', (open) => {
        if (!open) return;
        this.leadConfirmStep = false;
        this.selectedLeadName = '';
        this.selectedLeadValue = '';
        const none = document.getElementById('lead-none');
        if (none) none.checked = true;
      });
      this.$watch('showBulkMoveModal', (open) => {
        if (!open) return;
        this.moveConfirmStep = false;
        this.selectedMoveWorkspaceName = '';
        this.selectedMoveWorkspaceValue = '';
      });
    },
  };
}

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
  };
}

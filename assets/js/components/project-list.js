export default function projectList() {
  return {
    selectedCount: 0,
    showBulkDeleteModal: false,
    showBulkLeadModal: false,
    showCascadeModal: false,
    leadConfirmStep: false,
    selectedLeadName: '',
    selectedLeadValue: '',
    showFiltersModal: false,
    showNewProjectModal: false,
  };
}

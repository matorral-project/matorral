import Alpine from 'alpinejs';
import issueList from './components/issue-list.js';
import issuesEmbed from './components/issues-embed.js';

window.Alpine = Alpine;

Alpine.data('issueList', issueList);
Alpine.data('issuesEmbed', issuesEmbed);

document.addEventListener('DOMContentLoaded', () => {
    Alpine.start();
});

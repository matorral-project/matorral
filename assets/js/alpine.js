import Alpine from 'alpinejs';
import epicsEmbed from './components/epics-embed.js';
import issueList from './components/issue-list.js';
import issuesEmbed from './components/issues-embed.js';
import projectList from './components/project-list.js';
import sprintList from './components/sprint-list.js';

window.Alpine = Alpine;

Alpine.data('epicsEmbed', epicsEmbed);
Alpine.data('issueList', issueList);
Alpine.data('issuesEmbed', issuesEmbed);
Alpine.data('projectList', projectList);
Alpine.data('sprintList', sprintList);

document.addEventListener('DOMContentLoaded', () => {
    Alpine.start();
});

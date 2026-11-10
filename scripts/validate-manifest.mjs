#!/usr/bin/env node
// Validates manifest.json and the playbook folders it points at.
// Usage: node scripts/validate-manifest.mjs
// Exits 1 when any error is found. Warnings never fail the run.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const manifestPath = path.join(root, 'manifest.json');

// Built-in Maestro template variables (src/shared/templateVariables.ts). A launch
// input with one of these names would shadow the built-in, so it is rejected.
// Every CUE_* name is reserved as well.
const BUILT_INS = new Set(
	'ADDITIONAL_DIRECTORIES AGENT_DEEP_LINK AGENT_GROUP AGENT_HISTORY_PATH AGENT_ID AGENT_NAME AGENT_PATH AGENT_SESSION_ID AUTORUN_FOLDER CONDUCTOR_PROFILE CONTEXT_USAGE CWD DATE DATETIME DATE_SHORT DAY DOCUMENT_NAME DOCUMENT_PATH GIT_BRANCH GOAL GOAL_EXIT_CRITERIA GROUP_DEEP_LINK IS_GIT_REPO LOOP_NUMBER LOOP_NUMBER_HUMAN MAESTRO_CLI_PATH MONTH PREDECESSOR_HANDOFF TAB_DEEP_LINK TAB_ID TAB_NAME TIME TIMESTAMP TIME_SHORT TOOL_TYPE WEEKDAY WORKTREE_BASE_PATH YEAR'.split(
		' '
	)
);
const INPUT_TYPES = new Set(['text', 'textarea', 'url', 'path', 'number', 'boolean', 'select', 'multiselect']);
const PLATFORMS = new Set(['darwin', 'linux', 'win32']);
const REQUIRED_FIELDS = ['id', 'title', 'description', 'category', 'author', 'lastUpdated', 'path', 'documents'];
const HARDCODED_CLI = /node\s+"\/Applications\/Maestro\.app\/Contents\/Resources\/maestro-cli\.js"/;

const errors = [];
const warnings = [];
const err = (id, msg) => errors.push(`${id}: ${msg}`);
const warn = (id, msg) => warnings.push(`${id}: ${msg}`);

/** `**NAME:** `value`` lines in a prompt, the convention the launch flow rewrites. */
function configureLines(prompt) {
	const names = new Map();
	for (const match of (prompt || '').matchAll(/^\*\*([A-Z0-9_]+):\*\*\s*`([^`]*)`/gm)) {
		names.set(match[1], match[2]);
	}
	return names;
}

/** The text Maestro writes into a configuration line for an input's default. */
function serializeDefault(input) {
	const value = input.default;
	if (input.type === 'boolean') return value ? 'yes' : 'no';
	if (input.type === 'multiselect') {
		const list = [].concat(value);
		return list.length ? list.join(',') : (input.emptyValue ?? '');
	}
	if (input.type === 'number') return `${value}${input.unit ?? ''}`;
	return String(value).replace(/\s*\n\s*/g, ' ');
}

function taskDocs(dir) {
	if (!fs.existsSync(dir)) return [];
	return fs.readdirSync(dir).filter((f) => f.endsWith('.md') && f !== 'README.md');
}

function validateLaunch(p, launch, docTexts) {
	const id = p.id;
	if (typeof launch !== 'object' || launch === null || Array.isArray(launch)) {
		err(id, 'launch must be an object');
		return;
	}
	const pre = launch.preconditions ?? {};
	if (pre.platforms && !(Array.isArray(pre.platforms) && pre.platforms.every((x) => PLATFORMS.has(x)))) {
		err(id, `preconditions.platforms must be a list of ${[...PLATFORMS].join(', ')}`);
	}
	if (pre.requires && !(Array.isArray(pre.requires) && pre.requires.every((x) => typeof x === 'string'))) {
		err(id, 'preconditions.requires must be a list of strings');
	}
	if (pre.confirm !== undefined && typeof pre.confirm !== 'string') err(id, 'preconditions.confirm must be a string');
	if (pre.maestroCli !== undefined && !['required', 'optional'].includes(pre.maestroCli)) {
		err(id, 'preconditions.maestroCli must be "required" or "optional"');
	}
	const mentionsCli = docTexts.some((t) => t.includes('maestro-cli') || t.includes('{{MAESTRO_CLI_PATH}}'));
	if (mentionsCli && !pre.maestroCli) err(id, 'documents call maestro-cli but launch.preconditions.maestroCli is not declared');

	if (!Array.isArray(launch.inputs)) {
		err(id, 'launch.inputs must be a list (it may be empty)');
		return;
	}
	const configured = configureLines(p.prompt);
	const seen = new Set();
	for (const input of launch.inputs) {
		const where = `${id} input ${input?.name ?? '?'}`;
		if (!/^[A-Z][A-Z0-9_]*$/.test(input?.name ?? '')) {
			errors.push(`${where}: name must be UPPER_SNAKE_CASE`);
			continue;
		}
		if (seen.has(input.name)) errors.push(`${where}: duplicate name`);
		seen.add(input.name);
		if (BUILT_INS.has(input.name) || input.name.startsWith('CUE_')) errors.push(`${where}: collides with a built-in template variable`);
		if (!configured.has(input.name)) errors.push(`${where}: no **${input.name}:** line in the manifest prompt`);
		if (typeof input.label !== 'string' || !input.label) errors.push(`${where}: label is required`);
		if (!INPUT_TYPES.has(input.type)) {
			errors.push(`${where}: unknown type "${input.type}"`);
			continue;
		}
		const isChoice = input.type === 'select' || input.type === 'multiselect';
		if (isChoice) {
			if (!Array.isArray(input.options) || input.options.length === 0) {
				errors.push(`${where}: ${input.type} needs options`);
			} else {
				const values = new Set(input.options.map((o) => o?.value));
				const defaults = input.default === undefined ? [] : [].concat(input.default);
				for (const d of defaults) if (!values.has(d)) errors.push(`${where}: default "${d}" is not an option`);
				if (input.type === 'select' && Array.isArray(input.default)) errors.push(`${where}: select default must be one value`);
			}
		} else if (input.options !== undefined) {
			errors.push(`${where}: options only apply to select and multiselect`);
		}
		if (input.type === 'number') {
			if (input.default !== undefined && typeof input.default !== 'number') errors.push(`${where}: number default must be a number`);
			if (input.min !== undefined && input.max !== undefined && input.min > input.max) errors.push(`${where}: min is above max`);
			if (typeof input.default === 'number') {
				if (input.min !== undefined && input.default < input.min) errors.push(`${where}: default is below min`);
				if (input.max !== undefined && input.default > input.max) errors.push(`${where}: default is above max`);
			}
		} else if (input.min !== undefined || input.max !== undefined || input.unit !== undefined) {
			errors.push(`${where}: min, max and unit only apply to number`);
		}
		if (input.type === 'boolean' && input.default !== undefined && typeof input.default !== 'boolean') {
			errors.push(`${where}: boolean default must be true or false`);
		}
		if (input.emptyValue !== undefined && input.type !== 'multiselect') errors.push(`${where}: emptyValue only applies to multiselect`);
		if (input.pattern !== undefined) {
			try {
				const re = new RegExp(input.pattern);
				if (typeof input.default === 'string' && !re.test(input.default)) errors.push(`${where}: default does not match pattern`);
			} catch {
				errors.push(`${where}: pattern is not a valid regular expression`);
			}
		}
		const defaultText = [].concat(input.default ?? []).join(',');
		if (defaultText.includes('`')) errors.push(`${where}: default cannot contain a backtick`);
		if (input.required && input.default !== undefined) warn(id, `input ${input.name} is required and also has a default`);
		// Launching with every default must write exactly what Download ships, so the
		// two paths never diverge.
		if (input.default !== undefined && configured.has(input.name)) {
			const written = serializeDefault(input);
			if (written !== configured.get(input.name)) {
				errors.push(`${where}: default writes "${written}" but the prompt line says "${configured.get(input.name)}"`);
			}
		}
	}
	for (const name of configured.keys()) {
		if (!seen.has(name)) warn(id, `prompt configures ${name} but launch.inputs does not ask for it`);
	}

	if (launch.maxLoops !== undefined && launch.maxLoops !== null && !(Number.isInteger(launch.maxLoops) && launch.maxLoops > 0)) {
		err(id, 'launch.maxLoops must be a positive integer or null');
	}
	if (launch.cleanup !== undefined && !['remove-docs', 'keep'].includes(launch.cleanup)) {
		err(id, 'launch.cleanup must be "remove-docs" or "keep"');
	}
	const outro = launch.outro;
	if (!outro || typeof outro.summary !== 'string' || !outro.summary) {
		err(id, 'launch.outro.summary is required');
		return;
	}
	if (!Array.isArray(outro.nextSteps) || !outro.nextSteps.every((s) => typeof s === 'string')) {
		err(id, 'launch.outro.nextSteps must be a list of strings');
	}
	const allText = docTexts.join('\n');
	const filePaths = [...(outro.files ?? []).map((f) => f?.path), outro.reportFile].filter(Boolean);
	for (const f of outro.files ?? []) {
		if (typeof f?.label !== 'string' || typeof f?.path !== 'string') err(id, 'each outro file needs a label and a path');
	}
	for (const p2 of filePaths) {
		const base = path.basename(p2).replace(/\{\{AGENT_NAME\}\}_\{\{DATE\}\}/, '');
		const probe = base.replace(/\.md$/, '');
		if (!allText.includes(probe)) warn(id, `outro file ${p2} is never mentioned by the playbook documents`);
	}
	const known = new Set([...BUILT_INS, ...seen]);
	const outroText = [outro.title, outro.summary, ...(outro.nextSteps ?? []), ...filePaths].join('\n');
	for (const match of outroText.matchAll(/\{\{([A-Z0-9_]+)\}\}/g)) {
		if (!known.has(match[1])) err(id, `outro uses {{${match[1]}}}, which is neither an input nor a built-in`);
	}
}

const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
if (!Array.isArray(manifest.playbooks)) {
	console.error('manifest.json: playbooks must be a list');
	process.exit(1);
}
const ids = new Set();
for (const p of manifest.playbooks) {
	const id = p.id ?? '(no id)';
	for (const field of REQUIRED_FIELDS) if (p[field] === undefined || p[field] === '') err(id, `missing ${field}`);
	if (ids.has(id)) err(id, 'duplicate id');
	ids.add(id);
	const dir = path.join(root, p.path ?? '');
	if (!fs.existsSync(dir)) {
		err(id, `path ${p.path} does not exist`);
		continue;
	}
	for (const doc of p.documents ?? []) {
		const name = doc.filename.endsWith('.md') ? doc.filename : `${doc.filename}.md`;
		if (!fs.existsSync(path.join(dir, name))) err(id, `document ${name} not found in ${p.path}`);
	}
	// Maestro copies only the files listed in `assets`, so an unlisted file never
	// reaches the user and a listed but missing one fails its download.
	const assetsDir = path.join(dir, 'assets');
	const onDisk = fs.existsSync(assetsDir)
		? fs.readdirSync(assetsDir).filter((f) => !f.startsWith('.') && fs.statSync(path.join(assetsDir, f)).isFile())
		: [];
	const listed = p.assets ?? [];
	if (!Array.isArray(listed)) err(id, 'assets must be a list of file names');
	else {
		for (const f of onDisk) if (!listed.includes(f)) err(id, `assets/${f} exists but is not listed in assets`);
		for (const f of listed) if (!onDisk.includes(f)) err(id, `assets lists ${f}, which is not in ${p.path}/assets`);
	}
	const docs = taskDocs(dir);
	const docTexts = docs.map((f) => fs.readFileSync(path.join(dir, f), 'utf8'));
	docs.forEach((f, i) => {
		if (HARDCODED_CLI.test(docTexts[i])) err(id, `${f} hardcodes the macOS maestro-cli path; use {{MAESTRO_CLI_PATH}}`);
	});
	const promptFile = path.join(dir, 'Agent-Prompt.md');
	if (fs.existsSync(promptFile) && fs.readFileSync(promptFile, 'utf8').trim() !== (p.prompt ?? '').trim()) {
		err(id, 'manifest prompt does not match Agent-Prompt.md');
	}
	if (p.launch !== undefined) validateLaunch(p, p.launch, docTexts);
}

for (const w of warnings) console.log(`warning  ${w}`);
for (const e of errors) console.log(`error    ${e}`);
console.log(`\n${manifest.playbooks.length} playbooks, ${errors.length} errors, ${warnings.length} warnings`);
process.exit(errors.length ? 1 : 0);

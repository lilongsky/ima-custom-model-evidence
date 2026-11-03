const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '..');
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const errors = [];
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'evidence/source-manifest.json')));
for (const part of manifest.fragments) {
  const file = path.resolve(root, part.path);
  if (!file.startsWith(root + path.sep)) throw new Error('Manifest path escapes repository');
  const data = fs.readFileSync(file);
  if (data.length !== part.byte_length || sha(data) !== part.sha256) errors.push(`Fragment mismatch: ${part.id}`);
  const parent = manifest.sources.find(source => source.id === part.source_id);
  if (!parent || parent.sha256 !== part.parent_sha256) errors.push(`Parent identity mismatch: ${part.id}`);
  if (part.offsets.utf8_byte_end - part.offsets.utf8_byte_start !== data.length) errors.push(`Byte range mismatch: ${part.id}`);
}
const checksumPath = path.join(root, 'SHA256SUMS');
if (!fs.existsSync(checksumPath)) errors.push('Missing SHA256SUMS');
else for (const line of fs.readFileSync(checksumPath, 'utf8').trim().split('\n')) {
  const match = /^([a-f0-9]{64})  (.+)$/.exec(line);
  if (!match) { errors.push('Invalid checksum entry'); continue; }
  const file = path.resolve(root, match[2]);
  if (!file.startsWith(root + path.sep)) throw new Error('Checksum path escapes repository');
  if (!fs.existsSync(file) || sha(fs.readFileSync(file)) !== match[1]) errors.push(`Checksum mismatch: ${match[2]}`);
}
const claims = JSON.parse(fs.readFileSync(path.join(root, 'evidence/claims.json')));
for (const claim of claims.claims) for (const file of claim.local_evidence) {
  if (!fs.existsSync(path.join(root, file))) errors.push(`Missing claim evidence: ${claim.id} -> ${file}`);
}
if (errors.length) { console.error(errors.join('\n')); process.exitCode = 1; }
else console.log(`Verified ${manifest.sources.length} source identities, ${manifest.fragments.length} exact fragments, published file checksums, and ${claims.claims.length} claim mappings.`);

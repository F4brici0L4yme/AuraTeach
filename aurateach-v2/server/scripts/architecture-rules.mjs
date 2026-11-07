import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const ts = require('typescript');

function listTypeScriptFiles(directory) {
  if (!fs.existsSync(directory)) return [];
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) return listTypeScriptFiles(fullPath);
    return entry.isFile() && /\.tsx?$/.test(entry.name) ? [fullPath] : [];
  });
}

function importedModules(sourceFile) {
  const imports = [];
  const visit = (node) => {
    if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) {
      if (node.moduleSpecifier && ts.isStringLiteral(node.moduleSpecifier)) {
        imports.push(node.moduleSpecifier.text);
      }
    } else if (ts.isImportEqualsDeclaration(node)) {
      const reference = node.moduleReference;
      if (
        ts.isExternalModuleReference(reference) &&
        reference.expression &&
        ts.isStringLiteral(reference.expression)
      ) {
        imports.push(reference.expression.text);
      }
    } else if (ts.isCallExpression(node)) {
      const isDynamicImport = node.expression.kind === ts.SyntaxKind.ImportKeyword;
      const isRequire = ts.isIdentifier(node.expression) && node.expression.text === 'require';
      if (
        (isDynamicImport || isRequire) &&
        node.arguments[0] &&
        ts.isStringLiteral(node.arguments[0])
      ) {
        imports.push(node.arguments[0].text);
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return imports;
}

function configuredPathAliases(sourceRoot) {
  const configPath = path.resolve(sourceRoot, '../tsconfig.json');
  if (!fs.existsSync(configPath)) return [];
  const config = ts.readConfigFile(configPath, ts.sys.readFile);
  if (config.error) return [];
  const parsed = ts.parseJsonConfigFileContent(config.config, ts.sys, path.dirname(configPath));
  const baseUrl = path.resolve(path.dirname(configPath), parsed.options.baseUrl || '.');
  return Object.entries(parsed.options.paths || {}).map(([pattern, targets]) => ({
    prefix: pattern.split('*')[0],
    suffix: pattern.split('*')[1] || '',
    baseUrl,
    targets,
  }));
}

function resolveSourcePath(importer, specifier, aliases) {
  let basePaths = [];
  if (specifier.startsWith('.')) {
    basePaths = [path.resolve(path.dirname(importer), specifier)];
  } else {
    for (const alias of aliases) {
      if (
        specifier.startsWith(alias.prefix) &&
        specifier.endsWith(alias.suffix)
      ) {
        const wildcard = specifier.slice(
          alias.prefix.length,
          specifier.length - alias.suffix.length,
        );
        basePaths.push(...alias.targets.map((target) =>
          path.resolve(alias.baseUrl, target.replace('*', wildcard)),
        ));
      }
    }
  }

  for (const basePath of basePaths) {
    const candidates = [
      basePath,
      basePath.replace(/\.js$/, '.ts'),
      basePath.replace(/\.js$/, '.tsx'),
      basePath.replace(/\.js$/, '.d.ts'),
      `${basePath}.ts`,
      `${basePath}.tsx`,
      `${basePath}.d.ts`,
      path.join(basePath, 'index.ts'),
      path.join(basePath, 'index.tsx'),
    ];
    const found = candidates.find((candidate) => fs.existsSync(candidate));
    if (found) return path.resolve(found);
  }
  return null;
}

function isPublicApiTarget(modulesRoot, targetFile) {
  if (!targetFile) return false;
  const segments = path.relative(modulesRoot, targetFile).split(path.sep);
  return segments.length === 2 &&
    (segments[1] === 'public-api.ts' || segments[1] === 'public-api.tsx');
}

/** Finds imports that break the hexagonal module boundaries. */
export function findArchitectureViolations(sourceRoot) {
  const modulesRoot = path.join(sourceRoot, 'modules');
  const aliases = configuredPathAliases(sourceRoot);
  const files = listTypeScriptFiles(modulesRoot);
  const violations = [];

  for (const file of files) {
    const relativeFile = path.relative(modulesRoot, file);
    const [moduleName, layer] = relativeFile.split(path.sep);
    if (!moduleName) continue;

    const parsed = ts.createSourceFile(
      file,
      fs.readFileSync(file, 'utf8'),
      ts.ScriptTarget.Latest,
      true,
    );
    for (const specifier of importedModules(parsed)) {
      const targetFile = resolveSourcePath(file, specifier, aliases);
      const targetRelative = targetFile
        ? path.relative(modulesRoot, targetFile).split(path.sep)
        : [];
      const targetModule = targetRelative[0];
      const targetLayer = targetRelative[1];
      const isInsideModules = Boolean(
        targetFile &&
        targetFile.startsWith(`${modulesRoot}${path.sep}`),
      );
      const isSameModuleCore = targetModule === moduleName &&
        ['domain', 'application'].includes(targetLayer);

      if (layer === 'domain' && (!isInsideModules || targetModule !== moduleName || targetLayer !== 'domain')) {
        violations.push(`${relativeFile} imports '${specifier}' from outside its domain core`);
      }

      if (layer === 'application' && !isSameModuleCore) {
        violations.push(`${relativeFile} imports '${specifier}' outside domain/application`);
      }

      if (
        isInsideModules &&
        targetModule !== moduleName &&
        !isPublicApiTarget(modulesRoot, targetFile)
      ) {
        violations.push(`${relativeFile} imports another module's internals via '${specifier}'`);
      }

      if (specifier.startsWith('.') && !targetFile) {
        violations.push(`${relativeFile} has an unresolved relative import '${specifier}'`);
      }
    }
  }

  return violations;
}

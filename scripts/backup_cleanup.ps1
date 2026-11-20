param([ValidateSet('prune', 'remove')][string]$Action)

$ErrorActionPreference = 'Stop'

function Assert-DirectoryPath([string]$Candidate) {
    $resolved = [IO.Path]::GetFullPath($Candidate)
    $current = $resolved
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or !$item.PSIsContainer) {
                throw "Unsafe backup directory: $current"
            }
        }
        $current = [IO.Path]::GetDirectoryName($current)
    }
    return $resolved
}

function Assert-Snapshot([string]$Target, [string]$Candidate) {
    $resolved = Assert-DirectoryPath $Candidate
    if ([IO.Path]::GetDirectoryName($resolved) -ne $Target -or
        [IO.Path]::GetFileName($resolved) -notmatch '\A[0-9]{8}-[0-9]{6}\z') {
        throw "Backup cleanup escaped its target: $resolved"
    }
    if (Test-Path -LiteralPath $resolved) {
        $pending = New-Object 'System.Collections.Generic.Stack[string]'
        $pending.Push($resolved)
        while ($pending.Count) {
            foreach ($item in Get-ChildItem -LiteralPath $pending.Pop() -Force) {
                if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                    throw "Backup cleanup refuses links and junctions: $($item.FullName)"
                }
                if ($item.PSIsContainer) { $pending.Push($item.FullName) }
            }
        }
    }
    return $resolved
}

try {
    $target = Assert-DirectoryPath $env:TDIR
    if ($Action -eq 'remove') {
        $destination = Assert-Snapshot $target $env:DEST
        if (Test-Path -LiteralPath $destination) {
            Remove-Item -LiteralPath $destination -Recurse -Force
        }
    } else {
        $keepCount = 0
        if (![int]::TryParse($env:KEEP, [ref]$keepCount) -or $keepCount -lt 1) {
            throw 'KEEP must be a positive integer'
        }
        $snapshots = @(Get-ChildItem -LiteralPath $target -Directory -Force |
            Where-Object { $_.Name -match '\A[0-9]{8}-[0-9]{6}\z' } |
            Sort-Object Name -Descending)
        $completeCount = 0
        $removals = @()
        foreach ($snapshot in $snapshots) {
            $complete = Test-Path -LiteralPath (Join-Path $snapshot.FullName 'COMPLETE') -PathType Leaf
            if ($complete) { $completeCount += 1 }
            if (!$complete -or $completeCount -gt $keepCount) {
                $removals += Assert-Snapshot $target $snapshot.FullName
            }
        }
        foreach ($destination in $removals) {
            $null = Assert-Snapshot $target $destination
            Remove-Item -LiteralPath $destination -Recurse -Force
        }
    }
} catch {
    Write-Error $_
    exit 1
}

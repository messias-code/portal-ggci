<#
.SYNOPSIS
    Conecta uma pasta do servidor GGCI (Samba) como unidade de rede no Windows.

.DESCRIPTION
    Resolve de uma vez os problemas que impedem o acesso ao Samba do servidor:
      - PowerShell aberto como administrador: a conexão feita ali fica invisível
        para o Explorer, que continua dizendo "Você não tem permissão".
      - Erro 1219: o Windows já tem uma conexão com o servidor usando outro usuário
        (geralmente a conta da empresa, de uma tentativa anterior pelo Explorer).
      - Usuário sem domínio: digitar só "labs" faz o Windows mandar "EMPRESA\labs",
        que o servidor não conhece. O script usa "WORKGROUP\labs".
    Só mexe nas conexões DESTE servidor; as outras unidades de rede (W:, etc.) ficam.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\conectar_samba.ps1
    (pergunta tudo: pastas, letra e senha)

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\conectar_samba.ps1 -Servidor 10.209.67.140 -Pasta Portal_GGCI_Prod -Letra Q
    (dentro da rede da empresa, pelo IP local)
#>
[CmdletBinding()]
param(
    # 100.105.72.79 = Tailscale (de qualquer lugar). 10.209.67.140 = rede local da empresa.
    [string]$Servidor = '100.105.72.79',
    [string]$Pasta,
    [string]$Letra,
    [string]$Usuario = 'labs'
)

$ErrorActionPreference = 'Stop'
$PASTAS = @('Portal_GGCI_Prod', 'Portal_GGCI_Dev', 'Portal_GGCI')

function Escrever($cor, $texto) { Write-Host "   $texto" -ForegroundColor $cor }

Write-Host ''
Escrever Cyan "Conexão com o Samba do servidor GGCI ($Servidor)"
Write-Host ''

# 1. Não pode ser administrador: o Explorer não enxerga as conexões feitas ali.
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
         ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($admin) {
    Escrever Yellow 'Este PowerShell está aberto como ADMINISTRADOR.'
    Escrever Yellow 'A unidade criada aqui não apareceria no Explorer. Feche esta janela,'
    Escrever Yellow 'abra o PowerShell normal (sem "Executar como administrador") e rode de novo.'
    exit 1
}

# 2. O servidor responde na porta do Samba?
Escrever Gray "Testando a porta 445 em $Servidor..."
$teste = Test-NetConnection -ComputerName $Servidor -Port 445 -WarningAction SilentlyContinue
if (-not $teste.TcpTestSucceeded) {
    Escrever Red "O servidor $Servidor não respondeu na porta 445."
    if ($Servidor -like '100.*') {
        Escrever Red 'Confira se o Tailscale está ligado e conectado nesta máquina.'
        Escrever Red 'Dentro da rede da empresa, tente: -Servidor 10.209.67.140'
    } else {
        Escrever Red 'Confira se você está na rede da empresa; fora dela use o Tailscale (padrão).'
    }
    exit 1
}
Escrever Green 'Servidor alcançado.'

# 3. Qual pasta e qual letra.
if (-not $Pasta) {
    Write-Host ''
    for ($i = 0; $i -lt $PASTAS.Count; $i++) { Escrever White "[$($i + 1)] $($PASTAS[$i])" }
    $escolha = Read-Host '   Número da pasta (Enter = 1)'
    if (-not $escolha) { $escolha = '1' }
    if ($escolha -notmatch '^\d+$' -or [int]$escolha -lt 1 -or [int]$escolha -gt $PASTAS.Count) {
        Escrever Red "Opção inválida: $escolha"
        exit 1
    }
    $Pasta = $PASTAS[[int]$escolha - 1]
}
if (-not $Letra) {
    $sugestao = @{ 'Portal_GGCI_Prod' = 'P'; 'Portal_GGCI_Dev' = 'D'; 'Portal_GGCI' = 'G' }[$Pasta]
    if (-not $sugestao) { $sugestao = 'P' }
    $Letra = Read-Host "   Letra da unidade (Enter = $sugestao)"
    if (-not $Letra) { $Letra = $sugestao }
}
$Letra = $Letra.TrimEnd(':').ToUpper()
$caminho = "\\$Servidor\$Pasta"

# A letra já é usada por OUTRO servidor? Então não mexe: escolha outra.
$ocupada = Get-SmbMapping -LocalPath "${Letra}:" -ErrorAction SilentlyContinue
if ($ocupada -and $ocupada.RemotePath -notlike "\\$Servidor\*") {
    Escrever Red "A letra ${Letra}: já está ligada a $($ocupada.RemotePath). Rode de novo e escolha outra letra."
    exit 1
}
if (-not $ocupada -and (Test-Path "${Letra}:\")) {
    Escrever Red "A letra ${Letra}: já é um disco desta máquina. Rode de novo e escolha outra letra."
    exit 1
}

# 4. Limpa SÓ as conexões e credenciais deste servidor (resolve o erro 1219).
Write-Host ''
Escrever Gray "Limpando conexões antigas com $Servidor..."
$antigas = (net use) | Select-String -Pattern ([regex]::Escape("\\$Servidor\") + '\S+') -AllMatches |
           ForEach-Object { $_.Matches.Value } | Sort-Object -Unique
foreach ($c in $antigas) { net use $c /delete /y 2>&1 | Out-Null; Escrever DarkGray "removida: $c" }
if ($ocupada) { net use "${Letra}:" /delete /y 2>&1 | Out-Null }
(cmdkey /list) | Select-String -Pattern ('(?i)(?:Destino|Target):\s*(\S*' + [regex]::Escape($Servidor) + '\S*)') |
    ForEach-Object { cmdkey "/delete:$($_.Matches[0].Groups[1].Value)" | Out-Null; Escrever DarkGray "credencial removida: $($_.Matches[0].Groups[1].Value)" }

# 5. Conecta. O "*" faz o próprio Windows pedir a senha, sem mostrá-la na tela.
Write-Host ''
Escrever White "Conectando $caminho em ${Letra}: como WORKGROUP\$Usuario"
Escrever White 'Digite a senha do servidor quando for pedida (nada aparece enquanto digita).'
$saida = net use "${Letra}:" $caminho "/user:WORKGROUP\$Usuario" '*' '/persistent:yes' 2>&1
$codigo = $LASTEXITCODE
$texto = ($saida | Out-String)

Write-Host ''
if ($codigo -eq 0) {
    Escrever Green "Pronto! A pasta $Pasta está em ${Letra}: e volta sozinha ao reiniciar o Windows."
    Start-Process explorer.exe "${Letra}:\"
    exit 0
}

$erro = [regex]::Match($texto, '(?i)(?:erro de sistema|system error)\s+(\d+)').Groups[1].Value
switch ($erro) {
    '86'   { Escrever Red 'Senha incorreta. Rode de novo com calma (a senha não aparece enquanto digita).' }
    '1326' { Escrever Red 'Usuário ou senha incorretos. Rode de novo.' }
    '1219' { Escrever Red 'O Windows ainda segura uma conexão antiga com este servidor.'
             Escrever Red 'Feche as janelas do Explorer abertas nele (ou faça logoff do Windows) e rode de novo.' }
    '67'   { Escrever Red "A pasta '$Pasta' não existe no servidor. Pastas: $($PASTAS -join ', ')" }
    '53'   { Escrever Red 'Caminho de rede não encontrado. Confira o Tailscale ou a rede da empresa.' }
    '5'    { Escrever Red 'Acesso negado. Peça ao responsável pelo servidor para conferir o usuário do Samba.' }
    default {
        Escrever Red "Não foi possível conectar (erro $erro). Mensagem do Windows:"
        Escrever Red $texto.Trim()
    }
}
exit 1

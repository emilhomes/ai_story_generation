const axios = require("axios");
const readline = require("readline");
const fs = require("fs");
const path = require("path");

const SERVIDOR_FLASK = "http://localhost:5000";
const FORGE_API_TXT2IMG = "http://127.0.0.1:7860/sdapi/v1/txt2img";

const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
});

// ============================================================
// CONFIGURAÇÃO DE DIRETÓRIOS
// ============================================================
let PASTA_SESSAO = "";

function prepararPastaSessao(seed) {
    const baseDir = path.join(__dirname, "historias_geradas");
    if (!fs.existsSync(baseDir)) fs.mkdirSync(baseDir);

    PASTA_SESSAO = path.join(baseDir, `sessao_${seed}`);
    if (!fs.existsSync(PASTA_SESSAO)) fs.mkdirSync(PASTA_SESSAO);
    console.log(`\n📂 Arquivos serão salvos em: ${PASTA_SESSAO}`);
}

function salvarImagem(base64, nomeArquivo) {
    const filePath = path.join(PASTA_SESSAO, nomeArquivo);
    const buffer = Buffer.from(base64, "base64");
    fs.writeFileSync(filePath, buffer);
    console.log(`      💾 Imagem salva em: ${filePath}`);
}

function registrarLog(conteudo) {
    const filePath = path.join(PASTA_SESSAO, "historia_completa.txt");
    fs.appendFileSync(filePath, conteudo + "\n");
}

function perguntar(texto) {
    return new Promise((resolve) => {
        rl.question(texto, resolve);
    });
}

let SEED_SESSAO = Math.floor(Math.random() * 1000000000);
let IMAGEM_REFERENCIA_GLOBAL = null; 

// ============================================================
// GERAÇÃO DE SEQUÊNCIA COM IP-ADAPTER
// ============================================================
async function gerarSequenciaStoryboard(promptsImagens, microcenasTextos, negativePrompt, numeroCena) {
    console.log(`\n🎨 Gerando Storyboard - Cena ${numeroCena} (${microcenasTextos.length} quadros)`);

    const seedCena = SEED_SESSAO; 

    for (let i = 0; i < promptsImagens.length; i++) {
        const promptAtual = promptsImagens[i];
        const acaoTexto = microcenasTextos[i];

        console.log(`   🎬 Quadro ${i + 1}: [${acaoTexto}]`);

        const payloadTxt = {
            prompt: promptAtual,
            negative_prompt: negativePrompt || "",
            steps: 28,                        
            width: 768,
            height: 768,
            sampler_name: "DPM++ 2M Karras",
            cfg_scale: 7.0,                   
            seed: seedCena,
            alwayson_scripts: {},
            override_settings: {
                "CLIP_stop_at_last_layers": 2
            }
        };

        try {
            const response = await axios.post(FORGE_API_TXT2IMG, payloadTxt, { 
                timeout: 180000,
                responseType: 'json'
            });

            if (response.data && response.data.images) {
                const nomeImg = `cena_${numeroCena}_quadro_${i + 1}.png`;
                salvarImagem(response.data.images[0], nomeImg);
                registrarLog(`[IMAGEM: ${nomeImg}] Prompt: ${promptAtual}`);
            }

            console.log(`      ✅ Quadro ${i + 1} concluído.`);
        } catch (err) {
            console.log(`      ❌ Erro no Quadro ${i + 1}:`, err.message);
        }
    }
}

// ============================================================
// COMUNICAÇÃO COM O SERVIDOR FLASK
// ============================================================
async function iniciarSessao(nome, tema, skill, genero) {
    try {
        const resp = await axios.post(`${SERVIDOR_FLASK}/iniciar_historia`, { 
            nome, 
            tema, 
            skill,
            genero
        });
        return resp.data;
    } catch (err) {
        console.log("❌ Erro ao conectar ao servidor Flask.");
        return null;
    }
}

async function escolherCena(session_id, node_id, escolha_idx, escolha_texto) {
    try {
        const resp = await axios.post(`${SERVIDOR_FLASK}/escolher`, {
            session_id,
            node_id,
            escolha_idx,
            escolha_texto
        });
        return resp.data;
    } catch (err) {
        console.log("❌ Erro ao escolher cena.");
        return null;
    }
}

function mostrarMenu(titulo, opcoes) {
    console.log(`\n--- ${titulo} ---`);
    opcoes.forEach((op, index) => {
        console.log(`${index + 1}. ${op}`);
    });
}

function mostrarOpcoes(opcoes) {
    mostrarMenu("SUA ESCOLHA", opcoes);
}

// ============================================================
// LOOP PRINCIPAL
// ============================================================
async function main() {
    let contadorCena = 1; // Inicializa o contador

    console.log("\n==================================================");
    console.log("🎬 NAO - EXPLORADORES DA HISTÓRIA");
    console.log("==================================================");

    const nome = await perguntar("Qual o nome da criança? ");
    
    const generos = ["Masculino", "Feminino"];
    mostrarMenu("QUAL O GÊNERO DO PERSONAGEM?", generos);
    const generoIdx = parseInt(await perguntar("Selecione (1-2): ")) - 1;
    const genero = generos[generoIdx] || "Masculino";

    const jornadas = [
        { label: "Alan Turing - Cambridge (1936)", value: "alan_turing", tema: "Cambridge (1936)" },
        { label: "Steve Jobs - Vale do Silício (Apple)", value: "steve_jobs", tema: "Vale do Silício (Apple)" },
        { label: "Katherine Johnson - NASA (NASA Langley)", value: "katherine_johnson", tema: "NASA (NASA Langley)" }
    ];

    mostrarMenu("ESCOLHA SUA JORNADA HISTÓRICA", jornadas.map(j => j.label));
    const jornadaIdx = parseInt(await perguntar("Selecione (1-3): ")) - 1;
    const jornadaEscolhida = jornadas[jornadaIdx] || jornadas[0];

    const tema = jornadaEscolhida.tema;
    const skill = jornadaEscolhida.value;

    console.log("\n⏳ Preparando o mundo e abrindo o livro...");
    const dados = await iniciarSessao(nome, tema, skill, genero);

    if (!dados || dados.status !== "sucesso") {
        console.log("Erro ao iniciar.");
        process.exit(0);
    }

    // AGORA SIM: Criamos a pasta com o ID que o servidor nos deu
    SEED_SESSAO = dados.session_id; 
    prepararPastaSessao(SEED_SESSAO);
    registrarLog(`ALUNO: ${nome}\nTEMA: ${tema}\nSKILL: ${skill}\nSESSION_ID: ${SEED_SESSAO}\n`);

    let session_id = dados.session_id;
    let node_id = dados.node_id;
    let temOpcoes = dados.tem_opcoes;
    const negative = dados.negative_prompt || "";

    console.log(`\n📖 CENA ${contadorCena}:`);
    console.log(dados.historia_original);
    registrarLog(`\n--- CENA ${contadorCena} ---\n${dados.historia_original}\n`);

    // Primeira cena: gerar o primeiro quadro SEM IP-Adapter (referência)
    if (dados.prompts_imagens && dados.prompts_imagens.length > 0) {
        console.log("\n📸 Gerando imagem de referência...");
        await gerarPrimeiroQuadro(dados.prompts_imagens[0], dados.microcenas_textos[0], negative);

        if (dados.prompts_imagens.length > 1) {
            const promptsRestantes = dados.prompts_imagens.slice(1);
            const microcenasRestantes = dados.microcenas_textos.slice(1);
            await gerarSequenciaStoryboard(promptsRestantes, microcenasRestantes, negative, contadorCena);
        }
    }

    // opcoes_atuais guarda SEMPRE as opções da cena mais recente
    let opcoes_atuais = dados.opcoes || [];
    if (temOpcoes) mostrarOpcoes(opcoes_atuais);

    while (temOpcoes) {
        const escolhaStr = await perguntar("\n👉 Escolha (1-2) ou sair: ");
        if (escolhaStr.toLowerCase() === "sair") break;

        const idx = parseInt(escolhaStr);
        if (isNaN(idx) || idx < 1 || idx > opcoes_atuais.length) {
            console.log("❌ Opção inválida.");
            continue;
        }

        contadorCena++;
        // CORREÇÃO: usa opcoes_atuais, não dados.opcoes (que ficaria preso na cena 1)
        const escolhaTexto = opcoes_atuais[idx - 1];
        console.log(`\n⏳ Você escolheu: "${escolhaTexto}"`);
        registrarLog(`\nESCOLHA DO USUÁRIO: ${escolhaTexto}`);

        const resposta = await escolherCena(session_id, node_id, idx - 1, escolhaTexto);
        if (!resposta || resposta.status !== "sucesso") {
            console.log("❌ Erro na escolha.");
            break;
        }

        node_id = resposta.node_id;
        temOpcoes = resposta.tem_opcoes;

        console.log(`\n📖 CENA ${contadorCena}:`);
        console.log(resposta.historia_original);
        registrarLog(`\n--- CENA ${contadorCena} ---\n${resposta.historia_original}\n`);

        if (resposta.prompts_imagens && resposta.prompts_imagens.length > 0) {
            await gerarSequenciaStoryboard(resposta.prompts_imagens, resposta.microcenas_textos, negative, contadorCena);
        }

        // CORREÇÃO: atualiza opcoes_atuais IMEDIATAMENTE para a próxima iteração
        opcoes_atuais = resposta.opcoes || [];

        if (temOpcoes) mostrarOpcoes(opcoes_atuais);
        else console.log("\n🎬 Fim da história!");
    }

    console.log(`\n✨ Sessão encerrada! Todos os arquivos estão em: ${PASTA_SESSAO}`);
    rl.close();
}

// ============================================================
// GERAÇÃO DO PRIMEIRO QUADRO (referência inicial)
// ============================================================
async function gerarPrimeiroQuadro(promptImagem, microcenaTexto, negativePrompt) {
    console.log(`   🎬 Quadro REFERÊNCIA: [${microcenaTexto}]`);

    const payloadTxt = {
        prompt: promptImagem,
        negative_prompt: negativePrompt || "",
        steps: 25,
        width: 768,
        height: 768,
        sampler_name: "DPM++ 2M Karras",
        cfg_scale: 7.0,
        seed: SEED_SESSAO + 1,
        save_images: true,
        send_images: true,
        override_settings: {
            "CLIP_stop_at_last_layers": 2
        }
    };

    try {
        const response = await axios.post(FORGE_API_TXT2IMG, payloadTxt, { 
            timeout: 120000,
            responseType: 'json'
        });

        if (response.data && response.data.images && response.data.images.length > 0) {
            IMAGEM_REFERENCIA_GLOBAL = response.data.images[0];

            // Salva fisicamente
            salvarImagem(IMAGEM_REFERENCIA_GLOBAL, "cena_1_referencia_global.png");
            registrarLog(`[IMAGEM: cena_1_referencia_global.png] Prompt: ${promptImagem}`);

            console.log(`      ✅ Quadro de referência gerado e salvo!`);
        }
    } catch (err) {
        console.log(`      ❌ Erro ao gerar quadro de referência.`, err.message);
    }
}

main();